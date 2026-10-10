"""Maps different names for the same piece of equipment across brands to a
single canonical name (see doc/arch/webScraping/Car_Price_List_Architecture.md,
Data Normalization section). Currently a small hand-written dictionary —
once more parsers are written, move it into a DB table (equipment_alias)
so it can be edited without a deployment."""

from __future__ import annotations

EQUIPMENT_ALIASES: dict[str, str] = {
    "acc": "adaptive_cruise_control",
    "adaptive cruise control": "adaptive_cruise_control",
    "distance assist": "adaptive_cruise_control",
    "matrix led": "matrix_led_headlights",
    "matrix led headlights": "matrix_led_headlights",
    "heated seats": "heated_seats",
    "vyhřívaná sedadla": "heated_seats",
}


class EquipmentNormalizer:
    """Maps a raw equipment name (per-brand text from the PDF) to a
    canonical name shared across brands. The alias dictionary currently
    lives in code; once more parsers are written, move it into a DB table
    (equipment_alias) so it can be edited without a deployment."""

    def __init__(self, aliases: dict[str, str] = EQUIPMENT_ALIASES) -> None:
        self._aliases = aliases

    def normalize(self, raw_name: str) -> str:
        """Args:
            raw_name: Equipment name exactly as it appeared in the source
                PDF (any casing/whitespace).

        Returns:
            The canonical name from the alias table if `raw_name` (lower-
            cased, trimmed) is a known alias; otherwise `raw_name`
            lowercased/trimmed with spaces replaced by underscores.
        """
        key = raw_name.strip().lower()
        return self._aliases.get(key, key.replace(" ", "_"))
