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


def test_invalid_key_error_does_not_point_non_admins_at_the_admin_only_button() -> None:
    from app.ui.i18n import STRINGS
    from app.ui.pages import error_message

    assert error_message("ai_invalid_key", is_admin=True) == STRINGS["chat"]["errors"]["ai_invalid_key"]
    non_admin_text = error_message("ai_invalid_key", is_admin=False)
    assert non_admin_text == STRINGS["chat"]["errors"]["ai_invalid_key_user"]
    assert "AI klíč" not in non_admin_text


def _leaf_paths(node: dict, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    for key, value in node.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            paths |= _leaf_paths(value, f"{path}.")
        else:
            paths.add(path)
    return paths


def _without_czech_only_plurals(paths: set[str]) -> set[str]:
    # English has no `few` plural form - see `plural_key`.
    return {path for path in paths if not path.endswith(".few")}


def test_english_has_exactly_the_czech_keys() -> None:
    from app.ui.i18n import STRINGS
    from app.ui.i18n_en import STRINGS_EN

    assert _without_czech_only_plurals(_leaf_paths(STRINGS)) == _leaf_paths(STRINGS_EN)


def test_english_strings_use_the_same_placeholders() -> None:
    import string

    from app.ui.i18n import STRINGS
    from app.ui.i18n_en import STRINGS_EN

    def placeholders(path: str, locale: dict) -> set[str]:
        node = locale
        for part in path.split("."):
            node = node[part]
        return {name for _, name, _, _ in string.Formatter().parse(node) if name}

    for path in _leaf_paths(STRINGS_EN):
        assert placeholders(path, STRINGS_EN) == placeholders(path, STRINGS), path


def test_t_defaults_to_czech_outside_a_ui_context() -> None:
    assert t("chat.send") == "Odeslat"


def test_t_takes_an_explicit_language() -> None:
    assert t("chat.send", lang="en") == "Send"


def test_use_language_overrides_the_current_language() -> None:
    from app.ui.i18n import current_language, use_language

    with use_language("en"):
        assert current_language() == "en"
        assert t("chat.send") == "Send"
    assert current_language() == "cs"


@pytest.mark.parametrize(
    ("count", "expected"), [(0, "0 matches for you"), (1, "1 match for you"), (3, "3 matches for you")]
)
def test_t_count_english(count: int, expected: str) -> None:
    assert t_count("results.title", count, lang="en") == expected
