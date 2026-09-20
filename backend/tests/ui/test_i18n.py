"""Covers app/ui/i18n.py - the ported cs.json plus its plural-form
selection (not unit-tested on the React side; i18next's plural resolution
was library code there, this port hand-rolls it - see i18n.py's
docstring for the Czech `one`/`few`/`other` rule).
"""

import pytest

from app.ui.i18n import plural_key, t, t_count


def test_t_looks_up_a_nested_string() -> None:
    assert t("chat.send") == "Odeslat"


def test_t_interpolates_kwargs() -> None:
    assert t("car.photoPlaceholder", make="Mazda", model="CX-5") == "fotka auta — Mazda CX-5"


def test_t_raises_for_unknown_path() -> None:
    with pytest.raises(KeyError):
        t("nope.not.a.real.path")


@pytest.mark.parametrize(
    ("count", "expected"),
    [(1, "one"), (2, "few"), (3, "few"), (4, "few"), (0, "other"), (5, "other"), (21, "other")],
)
def test_plural_key(count: int, expected: str) -> None:
    assert plural_key(count) == expected


def test_t_count_singular() -> None:
    assert t_count("results.title", 1) == "1 shoda pro vás"


def test_t_count_few() -> None:
    assert t_count("results.title", 3) == "3 shody pro vás"


def test_t_count_other() -> None:
    assert t_count("results.title", 7) == "7 shod pro vás"


def test_error_message_is_specific_for_ai_failures_and_generic_otherwise() -> None:
    from app.ui.i18n import STRINGS
    from app.ui.pages import error_message

    for code in STRINGS["chat"]["errors"]:
        assert error_message(code) == STRINGS["chat"]["errors"][code]
    assert error_message("ai_not_configured") == STRINGS["chat"]["aiNotConfigured"]
    assert error_message("unknown_error") == STRINGS["chat"]["genericError"]
