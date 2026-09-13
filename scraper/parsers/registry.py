"""Maps `parser_key` (from config/sources.yaml) to a parser class.

A new parser = a new entry here + a file in this directory, nothing else
in main.py needs to change.
"""
from __future__ import annotations

from .audi import AudiParser
from .base import BaseParser
from .bmw import BmwParser
from .cupra import CupraParser
from .dacia import DaciaParser
from .ford import FordParser
from .hyundai import HyundaiParser
from .kia import KiaParser
from .mazda import MazdaParser
from .mercedes_benz import MercedesBenzParser
from .mg import MgParser
from .opel import OpelParser
from .peugeot import PeugeotParser
from .renault import RenaultParser
from .skoda_ev import SkodaEvParser
from .skoda_ice import SkodaIceParser
from .toyota import ToyotaParser
from .volkswagen import VolkswagenParser
from .volkswagen_ev import VolkswagenEvParser

PARSERS: dict[str, type[BaseParser]] = {
    "skoda_ice": SkodaIceParser,
    "skoda_ev": SkodaEvParser,
    "volkswagen": VolkswagenParser,
    "volkswagen_ev": VolkswagenEvParser,
    "kia": KiaParser,
    "toyota": ToyotaParser,
    "hyundai": HyundaiParser,
    "mercedes-benz": MercedesBenzParser,
    "mazda": MazdaParser,
    "bmw": BmwParser,
    "dacia": DaciaParser,
    "ford": FordParser,
    "cupra": CupraParser,
    "renault": RenaultParser,
    "opel": OpelParser,
    "peugeot": PeugeotParser,
    "mg": MgParser,
    "audi": AudiParser,
}
