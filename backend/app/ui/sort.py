"""Client-side ordering for the results grid, ported from
frontend/src/utils/sortCars.ts. Used for every sort option in narrowed mode
(the AI-narrowed shortlist is always fully loaded, so client-side sorting
is correct) and for 'recommended'/'custom' in browsing mode; 'price_asc' /
'price_desc' / 'alpha' in browsing mode are instead pushed to the backend
(see app/ui/state.py's CatalogState) since only one page is loaded at a
time there.
"""

from app.schemas.vehicle import VehicleSummary

SORT_OPTIONS = ("recommended", "price_asc", "price_desc", "alpha", "custom")
BACKEND_SORT_OPTIONS = ("price_asc", "price_desc", "alpha")


def sort_cars(cars: list[VehicleSummary], sort: str, custom_order: list[int] | None = None) -> list[VehicleSummary]:
    """Orders `cars` for display. Does not mutate `cars`.

    Args:
        cars: Cars to order.
        sort: One of `SORT_OPTIONS`.
        custom_order: Configuration ids in the user's manually dragged
            order (see `app/ui/state.py`'s custom-order storage); only
            consulted when `sort == "custom"`. Cars not present in it keep
            their relative input order and sort after every car that is -
            Python's `sorted` is stable, so a partially-arranged list is
            fine.

    Returns:
        A new list in the requested order.
    """
    if sort == "price_asc":
        return sorted(cars, key=lambda c: c.price.amount)
    if sort == "price_desc":
        return sorted(cars, key=lambda c: c.price.amount, reverse=True)
    if sort == "alpha":
        return sorted(cars, key=_alpha_key)
    if sort == "custom":
        order = custom_order or []
        position = {config_id: index for index, config_id in enumerate(order)}
        return sorted(cars, key=lambda c: position.get(c.configuration_id, len(order)))
    return list(cars)


# Czech alphabetical order, single characters only - "ch" as one letter
# (between H and I) is the one thing this doesn't get right, since that
# needs a digraph-aware collator (PyICU or the OS's cs_CZ locale, both
# heavier/more fragile dependencies than this catalog's brand/model names
# justify - Škoda is the only real-world case in this dataset that's
# actually diacritic-sensitive, and single-character mapping already
# orders that correctly, just not anything hinging on "ch" specifically).
_CZECH_ORDER = "aábcčdďeéěfghiíjklmnňoópqrřsštťuúůvwxyýzž"
_CZECH_WEIGHT = {char: index for index, char in enumerate(_CZECH_ORDER)}


def _alpha_key(car: VehicleSummary) -> tuple[tuple[int, str], ...]:
    """Sort key for the 'alpha' option, using Czech collation order
    rather than raw Unicode codepoint order - the frontend's
    `localeCompare(..., 'cs')` equivalent. Plain codepoint order would
    place every diacritic letter (á, č, š, ž, ...) after 'z', which is
    wrong often enough to matter here: "Škoda" is a real brand in this
    catalog, not an edge case.

    Args:
        car: Vehicle to derive a sort key for.

    Returns:
        A tuple of `(czech_alphabet_position, original_char)` pairs for
        the case-folded "brand model trim" string - comparable
        character-by-character like a string, but ordered by Czech
        alphabet position first (falling back to codepoint order, via the
        second tuple element, for anything not in `_CZECH_ORDER`, e.g.
        spaces and digits).
    """
    text = f"{car.brand} {car.model} {car.trim}".casefold()
    return tuple((_CZECH_WEIGHT.get(char, len(_CZECH_ORDER) + ord(char)), char) for char in text)
