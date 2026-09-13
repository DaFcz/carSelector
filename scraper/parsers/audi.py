"""Parser for Audi's own web-configurator JSON API (verified against a
real response downloaded 2026-09-14 from konfigurator.audi.cz - see
scraper/tests/fixtures/audi_modelgroup.json). Unlike every other brand
here, there's no PDF at all - see discovery/audi.py's own module
docstring for why this reads a JSON API response instead, and
sources/registry.py's `content_type` field, which routes Audi's own
source through `JsonDownloader` rather than `PdfDownloader` and skips the
PDF-only release-date step in `ScraperPipeline._process_document`.

The response is `{"modelgroups": [...]}`; each modelgroup (e.g. "A3
Limuzína", "Q5 Sportback") has one or more `variants` (e.g. "A3", "Sline",
"S3", "RS3"), and each variant has one `models` entry per engine/
drivetrain combination actually sold - the finest granularity this API
exposes, and the thing an `ExtractedVariant` is built from here.

There is no dedicated "trim" field anywhere in this response - Audi's own
CZ configurator doesn't gate price behind named equipment tiers the way
Škoda's Style/Selection or Opel's Edition/GS/Ultimate do. There IS a real,
price-gating two-way split hiding in the `variant` level once several
groups are compared, though (`_classify_variant`, verified against every
one of the 22 modelgroups in the fixture, not just one):

1. A plain/base variant (e.g. "A3") and an "S line" one (e.g. "Sline") -
   the exact same engines, S line priced a fixed amount higher (e.g. "A3
   Limuzína TDI 110kW" at 975 900 Kč vs. "A3 Limuzína S line TDI 110kW" at
   1 037 900 Kč) - a genuine trim, kept as `trim="S line"` vs. `"Standard"`
   on the SAME `model`. The equipment-line/powertrain split isn't fully
   orthogonal, though: for some groups (A5/A6/Q5's own e-hybrid engines)
   "S line" is only offered bundled with the range-topping engine, as its
   own separate variant code ending "SPHEV" rather than a parallel "Sline"
   variant alongside a plain "...PHEV" one - both are read as `trim="S
   line"`/`"Standard"` respectively, same as the parallel-variant case.
2. A performance sub-model (S3, RS3, S5, RS5, S6, SQ5, SQ6, SQ8, RSQ8, "S
   e-tron GT", "RS e-tron GT", "RS e-tron GT performance" - `code` always
   starting "S" or "RS", excluding the "S line" trim itself) - promoted to
   its OWN `model` (`trim="Standard"`, no further sub-tiers of its own in
   this data), the same convention BMW's own M2/M4 already use here
   (`sources.yaml`'s own bmw entry) rather than being folded into the base
   model as an oddly-priced "trim". Its own display name comes from the
   variant's own `name` field, which - inconsistently across groups - is
   sometimes already a complete name ("S6 Sportback") and sometimes just
   the bare badge ("S3", needing the modelgroup's own remaining words,
   e.g. "Limuzína", appended) - `_classify_variant` tells the two apart by
   checking whether the badge and the modelgroup name already share a
   word, appending only when they share none.

`price` is `listPrice.gross` (incl. VAT, same convention as every PDF
brand's own price column here). `engine` is built from this API's own
structured fields (fuel type, displacement, power, gearbox name, electric
range, drivetrain) rather than any of its free-text designation fields,
which are themselves inconsistent in the same "sometimes includes the
model name, sometimes doesn't" way `variant.name` is - reusing structured
data sidesteps that entirely. `wheelDrive.name` ("Přední"/"Zadní"/
"quattro®") is kept in `variant_name` so `infer_drivetrain` (which
already had a `quattro` alternative in `_AWD_RE` and gained a "zadní" one
for MG) classifies it correctly without any Audi-specific change needed.

Powertrain is classified from `fuel.type`: "Plug-in hybrid" is PHEV;
"Benzin (mild) Hybrid"/"Diesel(mild) Hybrid" are MHEV; "Elektro" is EV;
plain "Benzin"/"Diesel" is ICE - the literal word "Diesel" already being
part of the engine text means `infer_fuel_type`'s existing diesel regex
(which has plain "diesel" as one of its own alternatives) classifies the
ICE diesel rows correctly with no Audi-specific fix needed there either.

There's no page number or per-row source date for a JSON response -
`source_page` is always `1` (documented placeholder, not a real page),
and `raw_text` holds that row's own JSON object (`json.dumps`) instead of
a PDF text line, so a row can still be traced back to its exact source
for verification the same way every PDF-based parser's own `raw_text`
does."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .base import BaseParser, ExtractedVariant

_WHITESPACE_RE = re.compile(r"\s+")
# "Q4 e-tron PI"/"Q4 Sportback e-tron PI" are the only two modelgroup
# names carrying this trailing internal-code artifact (verified against
# every group in the fixture) - their own variants' own `name` field
# ("Audi Q4 e-tron"/"Audi Q4 Sportback e-tron") doesn't have it, so it's
# stripped here rather than left in the catalog's own model name.
_TRAILING_PI_RE = re.compile(r"\s+PI$")


def _normalize_code(code: str) -> str:
    return _WHITESPACE_RE.sub("", code).lower()


def _strip_audi_prefix(name: str) -> str:
    """Some model groups (Q3/Q5/Q6/Q8's own variants, not A3/A5/A6/e-tron
    GT's) prefix every variant's own `name` with "Audi " redundantly -
    stripped so `f"{brand} {model} {trim}"` doesn't read "Audi Audi Q5"."""
    return name[5:].strip() if name.lower().startswith("audi ") else name


def _classify_variant(mg_name: str, variant: dict) -> tuple[str, str]:
    """Args:
        mg_name: The modelgroup's own `name` (e.g. "A3 Limuzína").
        variant: One entry from that modelgroup's own `variants` list.

    Returns:
        `(model, trim)` - see module docstring for the classification
        rules and why performance sub-models are promoted to their own
        `model` instead of becoming an oddly-priced trim of the base one.
    """
    code = _normalize_code(variant["code"])
    if code == "sline":
        return _strip_audi_prefix(mg_name), "S line"
    if code.endswith("sphev"):
        return _strip_audi_prefix(mg_name), "S line"
    if code.endswith("phev"):
        return _strip_audi_prefix(mg_name), "Standard"
    if code.startswith("rs") or code.startswith("s"):
        badge = variant["name"]
        if not (set(mg_name.lower().split()) & set(badge.lower().split())):
            remainder = mg_name.split(maxsplit=1)
            if len(remainder) > 1:
                badge = f"{badge} {remainder[1]}"
        return _strip_audi_prefix(badge), "Standard"
    return _strip_audi_prefix(mg_name), "Standard"


def _classify_powertrain(fuel_type: str) -> str:
    lowered = fuel_type.lower()
    if "plug-in" in lowered:
        return "PHEV"
    if "hybrid" in lowered:
        return "MHEV"
    if "elektro" in lowered:
        return "EV"
    return "ICE"


def _build_engine_text(model: dict) -> str:
    parts = [model["fuel"]["type"]]
    capacity = model.get("capacity")
    if capacity:
        parts.append(f"{capacity}l")
    kilowatt = model["power"]["kilowatt"]
    horsepower = model["power"]["horsePower"]
    if kilowatt and horsepower:
        parts.append(f"{kilowatt} kW / {horsepower} k")
    gear_name = model["gear"]["name"]
    if gear_name:
        parts.append(gear_name)
    range_km = model.get("electricalRangeCombined")
    if range_km:
        parts.append(f"dojezd {range_km} km")
    wheel_drive = model["wheelDrive"]["name"]
    if wheel_drive:
        parts.append(wheel_drive)
    return " ".join(str(part) for part in parts)


class AudiParser(BaseParser):
    brand = "audi"
    powertrain = "ICE"  # nominal default; the actual powertrain is per-row, see _classify_powertrain

    def parse(self, pdf_path: Path) -> list[ExtractedVariant]:
        """See module docstring for the response shape and the model/trim
        classification rules.

        Args:
            pdf_path: Local path to the downloaded JSON response (despite
                the parameter name inherited from `BaseParser` - see its
                own docstring).

        Returns:
            One `ExtractedVariant` per model+engine combination found in
            the response.
        """
        data = json.loads(pdf_path.read_bytes().decode("utf-8"))
        variants: list[ExtractedVariant] = []

        for modelgroup in data.get("modelgroups") or []:
            mg_name = _TRAILING_PI_RE.sub("", modelgroup["name"])
            for variant in modelgroup.get("variants") or []:
                model, trim = _classify_variant(mg_name, variant)
                for row in variant.get("models") or []:
                    price = row.get("listPrice", {}).get("gross")
                    if price is None:
                        continue
                    engine = _build_engine_text(row)

                    variants.append(
                        ExtractedVariant(
                            model=model,
                            trim=trim,
                            variant_name=f"{model} {trim} {engine}".strip(),
                            price=float(price),
                            currency="CZK",
                            source_page=1,
                            raw_text=json.dumps(row, ensure_ascii=False),
                            powertrain=_classify_powertrain(row["fuel"]["type"]),
                        )
                    )

        return variants
