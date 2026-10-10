"""Downloads the current Opel CZ personal-car price lists into
scraper/tests/fixtures/, for use as parser test fixtures (see
scraper/parsers/opel.py once it exists).

Needed as a manual, one-off step because opel.cz sits behind an Akamai WAF
that blocks automated downloads at the TLS/network-fingerprint level, not
just on missing headers - verified 2026-09-12: Windows' own curl.exe
(which uses the Schannel TLS stack) gets a 403 even with a complete,
realistic browser header set, while Python's `requests` (a different TLS
stack) gets a 200 with the exact same headers and URL. Run this with the
same Python environment the rest of the project uses (the repo-root venv -
`requests` is already a dependency there, see requirements.txt) - a
pip-less `curl`/PowerShell `Invoke-WebRequest`-based version would hit the
same Schannel block this script exists to route around.

The scraper's own normal downloader (scraper/downloaders/pdf_downloader.py)
uses this exact same header set for exactly this reason - once
`scraper/monitors/discovery/opel.py` can find these URLs on its own
(currently blocked the same way the HTML listing page is - a full browser
engine, not just headers, would be needed there), the regular
`python -m scraper.main` pipeline downloads them itself and this script
stops being needed. Until then, this is the manual substitute for
discovery: the target URLs are hardcoded below rather than found on the
listing page.

Usage:
    python scripts/download_opel_pricelists.py
"""

from pathlib import Path

import requests

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "scraper" / "tests" / "fixtures"
BASE_URL = "https://www.opel.cz/content/dam/opel/czech_republic/brochure-library/pricelists/2026/Q2"

# See module docstring - a bare request (or one with only a User-Agent)
# still gets a 403; this specific combination (verified 2026-09-12) is
# what clears the WAF. No `Referer` needed - `Sec-Fetch-Site: none` is
# what a real browser sends for a direct, un-referred navigation.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "sec-ch-ua": '"Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

# source filename (under BASE_URL) -> target filename (under FIXTURES_DIR).
# One personal-car source document per (model, powertrain) combination
# that has its own price list on opel.cz/nastroje/katalogy-a-ceniky.html -
# commercial vehicles (Combo Van/Vivaro Van/Movano and their electric
# versions) are out of scope, same convention as every other brand's own
# discoverer. "Astra_HB"/"Astra_ST" each already cover both their own ICE
# and Plug-in Hybrid trims in one document (verified against the listing
# page: both links point at the same file) - only the electric hatchback
# and Sports Tourer share a third, separate document ("Astra_Electric").
# Same for "Grandland" covering both ICE and Plug-in Hybrid.
DOCUMENTS = {
    "CZ_Corsa.pdf": "opel_corsa_cenik.pdf",
    "CZ_Corsa_Electric.pdf": "opel_corsa_electric_cenik.pdf",
    "CZ_Astra_HB.pdf": "opel_astra_hb_cenik.pdf",
    "CZ_Astra_ST.pdf": "opel_astra_st_cenik.pdf",
    "CZ_Astra_Electric.pdf": "opel_astra_electric_cenik.pdf",
    "CZ_Mokka.pdf": "opel_mokka_cenik.pdf",
    "CZ_Mokka_Electric.pdf": "opel_mokka_electric_cenik.pdf",
    "CZ_Frontera.pdf": "opel_frontera_cenik.pdf",
    "CZ_Frontera_Electric.pdf": "opel_frontera_electric_cenik.pdf",
    "CZ_Grandland.pdf": "opel_grandland_cenik.pdf",
    "CZ_Grandland_Electric.pdf": "opel_grandland_electric_cenik.pdf",
}


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    failures = []
    for source_name, target_name in DOCUMENTS.items():
        url = f"{BASE_URL}/{source_name}"
        target_path = FIXTURES_DIR / target_name
        print(f"Downloading {source_name} -> {target_name} ...", end=" ", flush=True)
        try:
            response = requests.get(url, headers=BROWSER_HEADERS, timeout=30)
            response.raise_for_status()
            if not response.content.startswith(b"%PDF"):
                raise ValueError(
                    f"response doesn't look like a PDF (Content-Type: {response.headers.get('Content-Type')})"
                )
            target_path.write_bytes(response.content)
            print(f"OK ({len(response.content):,} bytes)")
        except Exception as exc:  # noqa: BLE001 - report every failure, then continue with the rest
            print(f"FAILED: {exc}")
            failures.append(source_name)

    print()
    if failures:
        print(f"{len(failures)} of {len(DOCUMENTS)} file(s) failed: {', '.join(failures)}")
    else:
        print(f"All {len(DOCUMENTS)} price lists downloaded successfully to {FIXTURES_DIR}")


if __name__ == "__main__":
    main()
