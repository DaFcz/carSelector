"""Maps `parser_key` (from config/sources.yaml) to a discoverer class.

A new discoverer = a new entry here + a file in this directory, nothing
else in source_monitor.py needs to change. Same pattern as
`parsers/registry.py`.
"""
from __future__ import annotations

from .audi import AudiDiscoverer
from .base import BaseDiscoverer
from .bmw import BmwDiscoverer
from .cupra import CupraDiscoverer
from .dacia import DaciaDiscoverer
from .ford import FordDiscoverer
from .hyundai import HyundaiDiscoverer
from .kia import KiaDiscoverer
from .mazda import MazdaDiscoverer
from .mercedes_benz import MercedesBenzDiscoverer
from .mg import MgDiscoverer
from .opel import OpelDiscoverer
from .peugeot import PeugeotDiscoverer
from .renault import RenaultDiscoverer
from .skoda import SkodaDiscoverer
from .toyota import ToyotaDiscoverer
from .volkswagen import VolkswagenDiscoverer

DISCOVERERS: dict[str, type[BaseDiscoverer]] = {
    "skoda_ice": SkodaDiscoverer,
    "skoda_ev": SkodaDiscoverer,
    "volkswagen": VolkswagenDiscoverer,
    "volkswagen_ev": VolkswagenDiscoverer,
    "kia": KiaDiscoverer,
    "toyota": ToyotaDiscoverer,
    "hyundai": HyundaiDiscoverer,
    "mercedes-benz": MercedesBenzDiscoverer,
    "mazda": MazdaDiscoverer,
    "bmw": BmwDiscoverer,
    "dacia": DaciaDiscoverer,
    "ford": FordDiscoverer,
    "cupra": CupraDiscoverer,
    "renault": RenaultDiscoverer,
    "opel": OpelDiscoverer,
    "peugeot": PeugeotDiscoverer,
    "mg": MgDiscoverer,
    "audi": AudiDiscoverer,
}
