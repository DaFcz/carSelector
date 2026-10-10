"""PDF export of one vehicle's detail - the same content the detail dialog
(`app/ui/components/vehicle_detail_modal.py`) shows, as an A4 document to
print or take to a dealership - and of a comparison of 2-4 vehicles (the
comparison dialog's rows, landscape).

Built server-side with fpdf2 (pure Python, no Node.js - see the tech stack
in `doc/prompt/CLAUDE.md`). fpdf2's built-in fonts only cover Latin-1, so
Czech text (ř, ě, ů, ...) needs a Unicode TrueType font: `_find_fonts`
takes `PDF_FONT_PATH`/`PDF_FONT_BOLD_PATH` if set, else the first DejaVu
Sans / Arial found in the usual Linux, Windows and macOS locations. With no
such font the PDF still renders, with diacritics stripped.
"""

import re
import unicodedata
from datetime import date
from pathlib import Path

from fpdf import FPDF
from fpdf.fonts import FontFace

from app.core import config
from app.schemas.vehicle import VehicleDetail
from app.ui.compare import build_sections, vehicle_title, visible_rows
from app.ui.i18n import t
from app.ui.money import format_money
from app.ui.vehicle_format import co2_label, consumption_label, power_label

# (regular, bold) pairs, tried in order.
_FONT_CANDIDATES: list[tuple[str, str]] = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
]

# Approximate sRGB of doc/design-tokens.md's OKLCH colors.
_TEXT = (58, 47, 40)
_SUBTEXT = (122, 109, 100)
_BORDER = (236, 227, 216)
_PANEL_2 = (248, 244, 238)
_ACCENT = (47, 111, 196)

_FAMILY = "Body"


def _find_fonts() -> tuple[str, str] | None:
    """Returns:
    `(regular, bold)` TTF paths, or `None` if no Unicode font is
    available. A missing bold file falls back to the regular one.
    """
    if config.PDF_FONT_PATH:
        return config.PDF_FONT_PATH, config.PDF_FONT_BOLD_PATH or config.PDF_FONT_PATH
    for regular, bold in _FONT_CANDIDATES:
        if Path(regular).is_file():
            return regular, bold if Path(bold).is_file() else regular
    return None


def pdf_filename(detail: VehicleDetail) -> str:
    """Args:
        detail: The exported vehicle.

    Returns:
        An ASCII-only file name, e.g. `"skoda-kodiaq-style.pdf"` - safe in
        a `Content-Disposition` header on any browser/OS.
    """
    name = unicodedata.normalize("NFKD", f"{detail.brand} {detail.model} {detail.trim}")
    name = "".join(ch for ch in name if not unicodedata.combining(ch)).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", name).strip("-")
    return f"{slug or 'vuz'}.pdf"


class _VehiclePdf(FPDF):
    """A4 page with the app's name in the header and a disclaimer + page
    number in the footer."""

    def __init__(self, unicode_fonts: tuple[str, str] | None, orientation: str = "portrait") -> None:
        super().__init__(orientation=orientation, format="A4")
        self._unicode = unicode_fonts is not None
        if unicode_fonts is not None:
            self.add_font(_FAMILY, "", unicode_fonts[0])
            self.add_font(_FAMILY, "B", unicode_fonts[1])
            self._body_family = _FAMILY
        else:
            self._body_family = "helvetica"
        self.set_margins(18, 16, 18)
        self.set_auto_page_break(auto=True, margin=22)
        self.set_text_color(*_TEXT)
        self.set_draw_color(*_BORDER)

    def clean(self, text: str) -> str:
        """Makes `text` printable in the active font.

        Args:
            text: Any UI string.

        Returns:
            `text` with glyphs our fonts lack swapped for plain ones, and
            with diacritics stripped too when only the Latin-1 core font
            is available.
        """
        text = text.replace("₂", "2").replace("✓", "•")
        if self._unicode:
            return text
        for src, dst in (("–", "-"), ("…", "..."), ("•", "-"), ("·", "-"), ("×", "x"), ("\u00a0", " ")):
            text = text.replace(src, dst)
        text = unicodedata.normalize("NFKD", text)
        return text.encode("latin-1", "ignore").decode("latin-1")

    def use_font(self, size: float, bold: bool = False) -> None:
        self.set_font(self._body_family, "B" if bold else "", size)

    def header(self) -> None:
        self.use_font(9, bold=True)
        self.set_text_color(*_ACCENT)
        self.cell(0, 5, self.clean(t("header.brand")), new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*_TEXT)
        self.ln(3)

    def footer(self) -> None:
        self.set_y(-16)
        self.use_font(7.5)
        self.set_text_color(*_SUBTEXT)
        self.multi_cell(0, 3.5, self.clean(t("vehicleDetail.pdf.disclaimer")), new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 4, self.clean(t("vehicleDetail.pdf.page", page=self.page_no(), total="{nb}")), align="R")
        self.set_text_color(*_TEXT)

    def section_heading(self, title: str) -> None:
        self.ln(5)
        self.use_font(9.5, bold=True)
        self.set_text_color(*_SUBTEXT)
        self.cell(0, 6, self.clean(title.upper()), new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*_TEXT)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)

    def muted(self, text: str) -> None:
        self.use_font(9.5)
        self.set_text_color(*_SUBTEXT)
        self.multi_cell(0, 5, self.clean(text), new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*_TEXT)

    def table_rows(self, rows: list[tuple[str, str]], col_widths: tuple[int, int]) -> None:
        """Two-column table with no header row.

        Args:
            rows: `(left, right)` cell texts.
            col_widths: Relative widths of the two columns.
        """
        self.use_font(9.5)
        with self.table(
            col_widths=col_widths,
            first_row_as_headings=False,
            borders_layout="HORIZONTAL_LINES",
            line_height=5.5,
            padding=(1.2, 2),
            text_align=("LEFT", "RIGHT"),
        ) as table:
            for left, right in rows:
                row = table.row()
                row.cell(self.clean(left))
                row.cell(self.clean(right))


def build_vehicle_pdf(detail: VehicleDetail, today: date | None = None) -> bytes:
    """Renders `detail` as a PDF document.

    Args:
        detail: The vehicle to export, as loaded for the detail dialog.
        today: Date printed as "created on"; defaults to today (a
            parameter so tests get a stable document).

    Returns:
        The PDF file's bytes.
    """
    pdf = _VehiclePdf(_find_fonts())
    pdf.add_page()

    pdf.use_font(18, bold=True)
    pdf.multi_cell(0, 8, pdf.clean(f"{detail.brand} {detail.model} {detail.trim}"), new_x="LMARGIN", new_y="NEXT")
    pdf.use_font(13, bold=True)
    pdf.set_text_color(*_ACCENT)
    pdf.cell(0, 7, pdf.clean(format_money(detail.price)), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*_TEXT)
    pdf.use_font(8.5)
    pdf.set_text_color(*_SUBTEXT)
    created = (today or date.today()).strftime(t("common.dateFormat"))
    pdf.cell(0, 5, pdf.clean(t("vehicleDetail.pdf.created", date=created)), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*_TEXT)

    no_data = t("vehicleDetail.fields.noData")
    pt = detail.powertrain
    pdf.section_heading(t("vehicleDetail.sections.powertrain"))
    fields = [
        (t("vehicleDetail.fields.fuelType"), t(f"vehicleDetail.enums.fuelType.{pt.fuel_type.value}")),
        (t("vehicleDetail.fields.drivetrain"), t(f"vehicleDetail.enums.drivetrain.{pt.drivetrain.value}")),
        (t("vehicleDetail.fields.transmission"), pt.transmission),
        (t("vehicleDetail.fields.power"), power_label(pt)),
        (t("vehicleDetail.fields.consumption"), consumption_label(pt)),
        (t("vehicleDetail.fields.co2"), co2_label(pt)),
    ]
    pdf.use_font(9.5)
    with pdf.table(
        col_widths=(1, 2),
        first_row_as_headings=False,
        borders_layout="NONE",
        cell_fill_color=_PANEL_2,
        cell_fill_mode="ROWS",
        line_height=5.5,
        padding=(1.2, 2),
    ) as table:
        for label, value in fields:
            row = table.row()
            row.cell(pdf.clean(label), style=FontFace(color=_SUBTEXT))
            row.cell(pdf.clean(value if value is not None else no_data), style=FontFace(emphasis="BOLD"))

    pdf.section_heading(t("vehicleDetail.sections.colors"))
    if not detail.colors:
        pdf.muted(t("vehicleDetail.noColors"))
    else:
        color_rows = []
        for color in detail.colors:
            name = color.name
            if color.finish_type is not None:
                name += " · " + t(f"vehicleDetail.enums.colorFinish.{color.finish_type.value}")
            surcharge = (
                f"+{format_money(color.surcharge)}" if color.surcharge.amount > 0 else t("vehicleDetail.pdf.included")
            )
            color_rows.append((name, surcharge))
        pdf.table_rows(color_rows, (3, 1))

    pdf.section_heading(t("vehicleDetail.sections.standardEquipment"))
    if not detail.standard_equipment:
        pdf.muted(no_data)
    else:
        pdf.use_font(9.5)
        for item in detail.standard_equipment:
            pdf.multi_cell(0, 5, pdf.clean(f"•  {item}"), new_x="LMARGIN", new_y="NEXT")

    pdf.section_heading(t("vehicleDetail.sections.optionalEquipment"))
    if not detail.optional_equipment:
        pdf.muted(t("vehicleDetail.noOptionalEquipment"))
    else:
        pdf.table_rows(
            [
                (
                    f"{option.name} ({t(f'vehicleDetail.enums.optionCategory.{option.category.value}')})",
                    format_money(option.surcharge),
                )
                for option in detail.optional_equipment
            ],
            (3, 1),
        )

    pdf.section_heading(t("vehicleDetail.sections.priceHistory"))
    if not detail.price_history:
        pdf.muted(no_data)
    else:
        history_rows = []
        for point in detail.price_history:
            valid_to = point.valid_to.isoformat() if point.valid_to else t("vehicleDetail.priceHistory.current")
            price_text = format_money(point.price)
            if point.lowest_price_30d is not None:
                price_text += (
                    " ("
                    + t("vehicleDetail.priceHistory.lowestPrice30d", price=format_money(point.lowest_price_30d))
                    + ")"
                )
            history_rows.append((f"{point.valid_from.isoformat()} – {valid_to}", price_text))
        pdf.table_rows(history_rows, (1, 2))

    return bytes(pdf.output())


def comparison_pdf_filename(details: list[VehicleDetail]) -> str:
    """Args:
        details: The compared vehicles.

    Returns:
        An ASCII-only file name, e.g. `"porovnani-mazda-cx-5-prime-line-mazda-cx-5-centre-line.pdf"`.
    """
    slugs = [pdf_filename(detail).removesuffix(".pdf") for detail in details]
    return f"porovnani-{'-'.join(slugs)}"[:120].rstrip("-") + ".pdf"


def build_comparison_pdf(
    details: list[VehicleDetail],
    differences_only: bool,
    match_scores: dict[int, int] | None = None,
    today: date | None = None,
) -> bytes:
    """Renders a comparison as a landscape A4 table - the same rows the
    comparison dialog shows (see `app/ui/compare.py`), best values in bold
    accent.

    Args:
        details: The compared vehicles, one column each.
        differences_only: Leave out the rows where every car is the same,
            as the dialog's switch does.
        match_scores: AI match score per configuration id, if any.
        today: Date printed as "created on"; defaults to today.

    Returns:
        The PDF file's bytes.
    """
    pdf = _VehiclePdf(_find_fonts(), orientation="landscape")
    pdf.add_page()

    pdf.use_font(16, bold=True)
    pdf.cell(0, 8, pdf.clean(t("compare.pdf.title")), new_x="LMARGIN", new_y="NEXT")
    pdf.use_font(8.5)
    pdf.set_text_color(*_SUBTEXT)
    created = (today or date.today()).strftime(t("common.dateFormat"))
    pdf.cell(0, 5, pdf.clean(t("vehicleDetail.pdf.created", date=created)), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*_TEXT)
    pdf.ln(3)

    col_widths = (3, *([4] * len(details)))
    best = FontFace(emphasis="BOLD", color=_ACCENT)
    muted = FontFace(color=_SUBTEXT)
    section_face = FontFace(emphasis="BOLD", color=_SUBTEXT, fill_color=_PANEL_2)

    pdf.use_font(8.5)
    with pdf.table(
        col_widths=col_widths,
        first_row_as_headings=True,
        headings_style=FontFace(emphasis="BOLD", color=_TEXT),
        borders_layout="HORIZONTAL_LINES",
        line_height=4.6,
        padding=(1, 1.5),
        text_align="LEFT",
        repeat_headings=1,
    ) as table:
        heading = table.row()
        heading.cell("")
        for detail in details:
            heading.cell(pdf.clean(vehicle_title(detail) + "\n" + format_money(detail.price)))

        for section in build_sections(details, match_scores):
            rows = visible_rows(section, differences_only)
            if not rows:
                continue
            section_row = table.row()
            section_row.cell(pdf.clean(section.title.upper()), colspan=len(details) + 1, style=section_face)
            for row in rows:
                cells = table.row()
                cells.cell(pdf.clean(row.label), style=muted)
                for index, cell in enumerate(row.cells):
                    cells.cell(pdf.clean(cell.text), style=best if index in row.best else None)

    return bytes(pdf.output())
