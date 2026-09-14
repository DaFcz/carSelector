"""Parser for tesla.com's own web-configurator ("Design Studio") page
(verified against real pages downloaded 2026-09-14 from
https://www.tesla.com/cs_cz/modely/design and .../model3/design - see
scraper/tests/fixtures/tesla_modely_design.html and
tesla_model3_design.html). Like Audi, there's no downloadable price-list
PDF at all - unlike Audi, there's also no separate JSON API endpoint;
instead, the `/design` page's own HTML embeds a `const dataJson = {...}`
script holding the entire pricing/options catalog for that model as one
big (almost-strict) JSON blob - see `monitors/discovery/tesla.py`'s own
module docstring for why a page fetch has to land here at all rather than
on a clean API URL.

`dataJson` itself is JS, not JSON (e.g. one real trailing comma before its
own outermost closing brace), so this parser doesn't try to parse the
whole blob - it locates the `"Lexicon.<product_code>":` key (`product_code`
is Tesla's own short model code, "my" for Model Y, "m3" for Model 3) and
extracts just that key's own value via balanced-brace scanning
(`_extract_balanced_object`, string-literal-aware so a `{`/`}` inside a
quoted value doesn't throw off the depth count). That extracted value IS
strict, valid JSON on its own (verified: `json.loads` succeeds on it
directly, no cleanup needed) - the one trailing-comma issue upstream lives
outside this key entirely.

Within that Lexicon object, `options` is a flat map of every sellable
option code to its own record; the ones actually needed here are the
`group == "TRIM"` ones (Tesla's own configurator groups the model's whole
drivetrain+battery+trim tier into a single selectable "TRIM" option,
unlike every PDF-based brand's own separate trim/engine columns) - e.g.
Model Y's 4: base "Rear-Wheel Drive", "Premium" Long Range RWD, "Premium"
Long Range AWD ("Dual Motor"), and "Performance" AWD. Each TRIM option's
own `pricing` list carries a `"base"` entry (the trim's own price ADD-ON
over the model's cheapest trim - not a usable price on its own) and a
`"base_plus_trim"` entry, which IS the real, full, VAT-included CZK price
shown to the customer (cross-checked against every price rendered on the
live page for both models) - the one this parser reads. `extra_copy_
formatted.category` gives the trim's own display tier ("Premium"/
"Performance"); the cheapest/base trim of each model has no `category` at
all, read as `"Standard"` here (matching the convention used for Audi/BMW/
Peugeot's own base trims elsewhere in this scraper). `long_name` is
Tesla's own complete, human-authored display name for the trim (e.g.
"Model Y Premium Long Range s pohonem všech kol Dual Motor") - used
directly as `variant_name` (after normalizing the NBSP Tesla puts between
"Model" and the model letter/number to a plain space) rather than being
rebuilt from parts, since it already reads correctly and keeps the exact
drivetrain wording ("pohonem zadních kol"/"pohonem všech kol") that
`scripts/import_scraper_data.py`'s `infer_drivetrain` needs - that helper
gained a broader `_RWD_RE` (matching "zadní" AND its inflected forms like
"zadních", not just the bare word MG's own price tables use) and an
"všech kol" alternative on `_AWD_RE` for this brand, since Tesla's own
Czech wording doesn't match either regex's existing alternatives as-is.

`product` (the Lexicon's own top-level field, "my"/"m3") maps to a real
display model name via `_MODEL_NAMES`, since the JSON itself never spells
out "Model Y"/"Model 3" anywhere a parser could read directly.

Every Tesla model sold is electric - `powertrain` is always `"EV"`, no
per-row classification needed (unlike every other brand here). There's no
page number or per-row source date for this kind of response - `source_page`
is always `1` (documented placeholder, not a real page, same convention as
Audi's own JSON-based parser), and `raw_text` holds the option's own JSON
object (`json.dumps`) instead of a PDF text line, so a row can still be
traced back to its exact source for verification the same way every other
parser's own `raw_text` does."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .base import BaseParser, ExtractedVariant

_LEXICON_KEY_RE = re.compile(r'"Lexicon\.(\w+)":')

_MODEL_NAMES = {
    "my": "Model Y",
    "m3": "Model 3",
}


def _extract_balanced_object(text: str, start: int) -> str:
    """Args:
        text: Text to scan, already positioned so `text[start]` is the
            opening `{` of the JS/JSON object to extract.
        start: Index of that opening `{`.

    Returns:
        The substring from `start` up to and including the matching
        closing `}`, tracking string literals (with backslash-escapes) so
        a `{`/`}` inside a quoted value doesn't throw off the brace depth.
    """
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    raise ValueError("unbalanced braces: reached end of text before depth returned to 0")


def _extract_lexicon(html: str) -> tuple[str, dict]:
    """Args:
        html: The downloaded Design Studio page's own HTML text.

    Returns:
        `(product_code, lexicon)` - `product_code` is Tesla's own short
        model code read out of the matched key (e.g. `"my"`); `lexicon` is
        that key's own value, parsed as JSON (see module docstring for why
        this is safe despite the page's own `dataJson` wrapper not being
        strict JSON as a whole).

    Raises:
        ValueError: No `"Lexicon.<code>":` key was found in `html` at all
            (e.g. the page didn't render the expected script - a real
            layout change, not something to silently paper over).
    """
    match = _LEXICON_KEY_RE.search(html)
    if match is None:
        raise ValueError('no "Lexicon.<code>" key found in the downloaded page')
    value_start = html.index("{", match.end())
    lexicon_text = _extract_balanced_object(html, value_start)
    return match.group(1), json.loads(lexicon_text)


class TeslaParser(BaseParser):
    brand = "tesla"
    powertrain = "EV"

    def parse(self, pdf_path: Path) -> list[ExtractedVariant]:
        """See module docstring for the response shape and the trim/price
        extraction rules.

        Args:
            pdf_path: Local path to the downloaded Design Studio HTML page
                (despite the parameter name inherited from `BaseParser` -
                see its own docstring).

        Returns:
            One `ExtractedVariant` per TRIM-group option found for this
            model (4 for both Model Y and Model 3, as of the fixtures this
            was verified against).
        """
        html = pdf_path.read_text(encoding="utf-8")
        product_code, lexicon = _extract_lexicon(html)
        model = _MODEL_NAMES.get(product_code, product_code)

        variants: list[ExtractedVariant] = []
        for option in lexicon.get("options", {}).values():
            if option.get("group") != "TRIM":
                continue
            pricing = {p["type"]: p for p in option.get("pricing", [])}
            full_price = pricing.get("base_plus_trim")
            if full_price is None:
                continue

            trim = option.get("extra_copy_formatted", {}).get("category") or "Standard"
            variant_name = option["long_name"].replace("\xa0", " ")

            variants.append(
                ExtractedVariant(
                    model=model,
                    trim=trim,
                    variant_name=variant_name,
                    price=float(full_price["value"]),
                    currency=full_price.get("context", "CZK"),
                    source_page=1,
                    raw_text=json.dumps(option, ensure_ascii=False),
                    powertrain="EV",
                )
            )

        return variants
