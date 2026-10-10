"""Turns 2-4 vehicles' details into comparison rows - shared by the
comparison dialog (`app/ui/components/compare_dialog.py`) and its PDF
export (`app/ui/vehicle_pdf.py`), so both show the same rows, the same
"best in row" highlights, and hide the same rows in "differences only" mode.

Display text goes through `t()`/`format_money()` like everywhere else in the
UI layer; no NiceGUI here, so it's unit-testable on its own.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from app.schemas.vehicle import VehicleDetail
from app.ui.i18n import t
from app.ui.money import format_money
from app.ui.vehicle_format import co2_label, consumption_label, power_label

# Same bound as `GET /api/vehicles/compare` (doc/api-contract.md): more
# columns stop being readable, on a phone especially.
MAX_COMPARE = 4
MIN_COMPARE = 2

# Equipment cell kinds.
STANDARD = "standard"
OPTIONAL = "optional"
MISSING = "missing"


@dataclass
class CompareCell:
    """One car's value in a row. `kind` is only meaningful for equipment
    rows (`STANDARD` / `OPTIONAL` / `MISSING`); other rows use `"text"`."""

    text: str
    kind: str = "text"


@dataclass
class CompareRow:
    label: str
    cells: list[CompareCell]
    # Indexes of the cells holding the row's best value (cheapest,
    # strongest, ...) - empty when the row has no "better" direction or
    # every car is equal.
    best: set[int] = field(default_factory=set)

    @property
    def differs(self) -> bool:
        """Whether the cars differ in this row - "differences only" mode
        hides the rows where they don't."""
        return len({(cell.kind, cell.text) for cell in self.cells}) > 1


@dataclass
class CompareSection:
    title: str
    rows: list[CompareRow]


def _best(values: list[float | None], *, lowest: bool) -> set[int]:
    """Args:
        values: One comparable number per car (`None` = unknown).
        lowest: Whether lower is better.

    Returns:
        Indexes holding the best value - empty unless at least two cars
        have a value and they aren't all equal (nothing to point out).
    """
    known = [value for value in values if value is not None]
    if len(known) < 2 or len(set(known)) == 1:
        return set()
    target = min(known) if lowest else max(known)
    return {index for index, value in enumerate(values) if value == target}


def _text_row(label: str, texts: list[str | None], best: set[int] | None = None) -> CompareRow:
    no_data = t("vehicleDetail.fields.noData")
    return CompareRow(label, [CompareCell(text if text is not None else no_data) for text in texts], best or set())


def same_brand(details: list[VehicleDetail]) -> bool:
    """Equipment names only line up within one brand (each manufacturer
    words its price lists differently), so equipment is compared row by
    row only then - see `equipment_rows`.

    Args:
        details: The compared vehicles.

    Returns:
        Whether they all come from one brand.
    """
    return len({detail.brand for detail in details}) == 1


def _equipment_key(name: str) -> str:
    """Matching key for an equipment name - price lists of one brand don't
    always agree on capitalization or spacing ("LED" vs "led")."""
    return " ".join(name.casefold().split())


def equipment_rows(details: list[VehicleDetail]) -> list[CompareRow]:
    """One row per equipment item found on any of the cars, saying per car
    whether it's standard, an option (with its price) or unavailable.
    Names are matched ignoring case and spacing (see `_equipment_key`).

    Args:
        details: Vehicles of one brand (see `same_brand`).

    Returns:
        Rows in first-seen order: each car's standard equipment, then
        optional equipment - labelled with the first-seen spelling.
    """
    names: dict[str, str] = {}
    for detail in details:
        for name in detail.standard_equipment:
            names.setdefault(_equipment_key(name), name)
    for detail in details:
        for option in detail.optional_equipment:
            names.setdefault(_equipment_key(option.name), option.name)

    lookups = []
    for detail in details:
        standard = {_equipment_key(name) for name in detail.standard_equipment}
        optional = {_equipment_key(option.name): option for option in detail.optional_equipment}
        lookups.append((standard, optional))

    rows = []
    for key, name in names.items():
        cells = []
        prices: list[float | None] = []
        for standard, optional in lookups:
            if key in standard:
                cells.append(CompareCell(t("compare.standard"), STANDARD))
                prices.append(0.0)
            elif key in optional:
                surcharge = optional[key].surcharge
                cells.append(CompareCell(f"+ {format_money(surcharge)}", OPTIONAL))
                prices.append(surcharge.amount)
            else:
                cells.append(CompareCell(t("compare.missing"), MISSING))
                prices.append(None)
        rows.append(CompareRow(name, cells, _best(prices, lowest=True)))
    return rows


def _color_summary(detail: VehicleDetail) -> str:
    if not detail.colors:
        return t("vehicleDetail.noColors")
    surcharges = [color.surcharge for color in detail.colors]
    cheapest = min(surcharges, key=lambda money: money.amount)
    priciest = max(surcharges, key=lambda money: money.amount)
    if cheapest.amount == priciest.amount:
        price_range = format_money(cheapest)
    else:
        price_range = f"{format_money(cheapest)} – {format_money(priciest)}"
    return t("compare.colorSummary", count=len(detail.colors), range=price_range)


def build_sections(details: list[VehicleDetail], match_scores: Mapping[int, int] | None = None) -> list[CompareSection]:
    """Builds every comparison section for `details`.

    Args:
        details: The compared vehicles, one column each, in order.
        match_scores: AI match score per configuration id, if the cars
            came from a recommendation - the row is left out otherwise.

    Returns:
        Overview, powertrain, equipment (only for a single brand - see
        `same_brand`) and colors sections.
    """
    scores = match_scores or {}
    powertrains = [detail.powertrain for detail in details]

    overview = [
        _text_row(
            t("compare.rows.price"),
            [format_money(detail.price) for detail in details],
            _best([detail.price.amount for detail in details], lowest=True),
        )
    ]
    if any(detail.configuration_id in scores for detail in details):
        values = [scores.get(detail.configuration_id) for detail in details]
        overview.append(
            _text_row(
                t("compare.rows.matchScore"),
                [f"{value} %" if value is not None else None for value in values],
                _best([float(value) if value is not None else None for value in values], lowest=False),
            )
        )

    same_unit = len({pt.consumption_unit for pt in powertrains}) == 1
    powertrain = [
        _text_row(
            t("vehicleDetail.fields.fuelType"),
            [t(f"vehicleDetail.enums.fuelType.{pt.fuel_type.value}") for pt in powertrains],
        ),
        _text_row(t("vehicleDetail.fields.transmission"), [pt.transmission for pt in powertrains]),
        _text_row(
            t("vehicleDetail.fields.drivetrain"),
            [t(f"vehicleDetail.enums.drivetrain.{pt.drivetrain.value}") for pt in powertrains],
        ),
        _text_row(
            t("vehicleDetail.fields.power"),
            [power_label(pt) for pt in powertrains],
            _best([pt.power_kw for pt in powertrains], lowest=False),
        ),
        _text_row(
            t("vehicleDetail.fields.consumption"),
            [consumption_label(pt) for pt in powertrains],
            _best([pt.consumption_min for pt in powertrains], lowest=True) if same_unit else set(),
        ),
        _text_row(
            t("vehicleDetail.fields.co2"),
            [co2_label(pt) for pt in powertrains],
            _best([pt.co2_min_g_km for pt in powertrains], lowest=True),
        ),
    ]

    sections = [
        CompareSection(t("compare.sections.overview"), overview),
        CompareSection(t("vehicleDetail.sections.powertrain"), powertrain),
    ]
    if same_brand(details):
        sections.append(CompareSection(t("compare.sections.equipment"), equipment_rows(details)))
    sections.append(
        CompareSection(
            t("vehicleDetail.sections.colors"),
            [_text_row(t("compare.rows.colors"), [_color_summary(detail) for detail in details])],
        )
    )
    return sections


def visible_rows(section: CompareSection, differences_only: bool) -> list[CompareRow]:
    """Args:
        section: A section from `build_sections`.
        differences_only: Hide the rows where every car is the same.

    Returns:
        The rows to show.
    """
    return [row for row in section.rows if row.differs] if differences_only else list(section.rows)


def vehicle_title(detail: VehicleDetail) -> str:
    return f"{detail.brand} {detail.model} {detail.trim}"


def default_trim_selection(prices: list[float], current_index: int, limit: int = MAX_COMPARE) -> set[int]:
    """Pre-ticks the trim picker: the current trim plus the trims nearest
    to it in price, up to `limit` in total.

    Args:
        prices: One price per trim.
        current_index: Index of the trim the user came from.
        limit: How many to pick.

    Returns:
        Indexes into `prices`.
    """
    order = sorted(range(len(prices)), key=lambda index: (abs(prices[index] - prices[current_index]), index))
    return set(order[:limit])
