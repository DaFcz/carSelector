"""Czech UI copy, ported verbatim from the former frontend's
`src/i18n/locales/cs.json`. Czech is the only language that ever shipped
(the React app's `en.json` existed but was never wired to a switcher) - see
`doc/prompt/CLAUDE.md`'s language convention. No i18n library: a plain
nested dict plus a small lookup/pluralization helper is enough for one
fixed language and keeps the UI layer dependency-free.
"""

STRINGS: dict = {
    "header": {
        "brand": "Rovis",
        "tagline": "Popište svůj životní styl. Najdeme vám auto.",
        "restart": "Restartovat",
        "technicalRequirements": "Technické požadavky",
        "startWizard": "Průvodce výběrem",
        "apiKey": "AI klíč",
        "apiKeyMissing": "AI klíč chybí",
        "login": "Přihlásit se",
        "logout": "Odhlásit",
    },
    "auth": {
        "title": "Přihlášení",
        "emailDescription": "Zadejte e-mail — pošleme vám jednorázový kód. Účet se vytvoří automaticky, heslo není potřeba.",
        "emailLabel": "E-mail",
        "sendCode": "Poslat kód",
        "sending": "Odesílám…",
        "codeDescription": "Poslali jsme šestimístný kód na {email}. Platí {minutes} minut.",
        "codeLabel": "Kód z e-mailu",
        "verify": "Potvrdit",
        "verifying": "Ověřuji…",
        "consoleNotice": (
            "Vývojový režim: e-mail se neodesílá, kód je vypsaný v logu serveru. "
            "Pro skutečné e-maily nastavte EMAIL_BACKEND=smtp a SMTP_* (viz README)."
        ),
        "resend": "Poslat nový kód",
        "changeEmail": "Změnit e-mail",
        "cancel": "Zrušit",
        "adminOnly": "Tato stránka je jen pro administrátory.",
        "adminOnlyLoggedIn": "Jste přihlášen(a) jako {email}, ale tento účet nemá administrátorská práva.",
        "backToApp": "← Zpět na appku",
        "errors": {
            "invalid_email": "Zadejte prosím platnou e-mailovou adresu.",
            "rate_limited": "Příliš mnoho požadavků na kód. Zkuste to prosím za chvíli.",
            "email_delivery_failed": "E-mail se nepodařilo odeslat. Zkuste to prosím znovu za chvíli.",
            "email_not_configured": "Odesílání e-mailů není nastavené (EMAIL_BACKEND / SMTP_* na serveru).",
            "invalid_code": "Kód není správný nebo mu vypršela platnost.",
            "too_many_attempts": "Příliš mnoho nesprávných pokusů. Pošlete si prosím nový kód.",
            "account_disabled": "Tento účet je zablokovaný.",
            "unknown_error": "Něco se nepovedlo. Zkuste to prosím znovu.",
        },
    },
    "apiKey": {
        "title": "API klíč pro AI ({provider})",
        "description": (
            "Klíč se uloží jen do paměti běžící aplikace — nikam na disk ani do zdrojových kódů. "
            "Po restartu aplikace ho bude potřeba zadat znovu."
        ),
        "label": "API klíč",
        "getKey": "Klíč získáte zdarma na {url}.",
        "configured": "AI klíč je nastavený.",
        "save": "Uložit",
        "cancel": "Zrušit",
        "clear": "Odebrat klíč",
        "empty": "Zadejte prosím klíč.",
        "invalid": (
            "Klíč obsahuje nepovolený znak „{char}“ na pozici {position}. Skutečný klíč je jen z "
            "písmen, číslic a podtržítek bez mezer — zkuste ho vložit znovu (Ctrl+V)."
        ),
    },
    "chat": {
        "typePlaceholder": "Napište odpověď…",
        "send": "Odeslat",
        "sending": "Přemýšlím…",
        "aiNotConfigured": (
            "AI vrstva zatím není nastavená (chybí API klíč) — konverzace funguje, "
            "ale bez rozpoznávání požadavků a doporučení."
        ),
        "genericError": "Něco se nepovedlo. Zkuste to prosím znovu.",
        "errors": {
            "ai_invalid_key": (
                "AI služba odmítla API klíč (neplatný nebo zrušený). "
                "Zadejte ho znovu přes tlačítko „AI klíč“ v záhlaví."
            ),
            # Shown instead of ai_invalid_key to non-admins, who can't reach the
            # "AI klíč" button (admin-only) that message points at.
            "ai_invalid_key_user": (
                "AI služba je dočasně nedostupná (neplatný API klíč na straně serveru). "
                "Dejte prosím vědět administrátorovi."
            ),
            "ai_rate_limited": "Byl překročen limit požadavků AI služby. Zkuste to prosím za chvíli.",
            "ai_model_unavailable": (
                "Zvolený AI model není dostupný. Zkontrolujte nastavení modelu (GROQ_MODEL / CLAUDE_MODEL)."
            ),
            "ai_unreachable": "Nepodařilo se spojit s AI službou. Zkontrolujte připojení k internetu.",
            "ai_error": "AI služba vrátila chybu. Zkuste to prosím znovu.",
        },
    },
    "wizard": {
        "title": "Průvodce výběrem auta",
        "subtitle": "Deset krátkých otázek — na konci vám rovnou ukážeme, co z katalogu vyhovuje.",
        "progress": "Otázka {step} z {total}",
        "back": "Zpět",
        "next": "Další",
        "skip": "Nevím / přeskočit",
        "finish": "Zobrazit doporučení",
        "close": "Zavřít",
        "summaryIntro": "Vyplnil(a) jsem průvodce",
        "questions": {
            "budget": {
                "title": "Jaký je váš rozpočet na nové auto?",
                "placeholder": "Např. 800000",
                "unit": "Kč",
                "summary": "rozpočet do {amount} Kč",
            },
            "usage": {
                "title": "K čemu auto nejčastěji použijete?",
                "options": {
                    "commute": "Dojíždění do práce",
                    "family": "Rodinné výlety",
                    "cargo": "Převoz nákladu",
                    "mixed": "Kombinace všeho",
                },
            },
            "seats": {
                "title": "Kolik lidí bude auto pravidelně vozit?",
                "placeholder": "Např. 5",
                "summary": "min. {count} míst",
            },
            "bodyType": {
                "title": "Jak má auto vypadat a jak velké má být?",
                "hint": (
                    "Menší auto do města, praktické kombi na časté cesty, vyšší SUV s lepším "
                    "výhledem, nebo velký rodinný vůz na 7 lidí."
                ),
                "options": {
                    "Hatchback": "Menší auto do města",
                    "Kombi": "Praktické kombi",
                    "SUV": "Vyšší SUV",
                    "MPV": "Velký rodinný vůz (7 míst)",
                },
            },
            "awd": {
                "title": "Jezdíte i tam, kde bývá bláto, sníh nebo horší cesta (chalupa, hory, pole)?",
                "hint": "Pokud ano, hodí se auto s pohonem všech kol – lépe drží na kluzkém povrchu.",
                "yes": "Ano, často",
                "no": "Ne, jezdím hlavně po silnicích",
            },
            "fuel": {
                "title": "Jak vypadá vaše typické jezdění?",
                "options": {
                    "electric": "Hlavně po městě na kratší vzdálenosti, můžu dobíjet doma nebo v práci",
                    "hybrid": "Kombinuji město i časté delší cesty",
                    "diesel": "Jezdím hodně a na dlouhé vzdálenosti (dálnice, služební cesty)",
                    "petrol": "Jezdím málo nebo nepravidelně, chci to mít jednoduché",
                },
            },
            "mileage": {
                "title": "Kolik kilometrů ročně přibližně najezdíte?",
                "placeholder": "Např. 15000",
                "summary": "roční nájezd přibližně {km} km",
            },
            "cargo": {
                "title": "Vozíte často něco objemného?",
                "options": {
                    "stroller": "Kočárek",
                    "sports": "Sportovní vybavení",
                    "tools": "Nářadí",
                    "trailer": "Táhnu přívěs nebo loď",
                    "none": "Nic z toho",
                },
            },
            "brand": {
                "title": "Preferujete konkrétní značku, nebo naopak nějakou vyloučit?",
                "placeholder": "Např. preferuji Škodu, nechci Fiat",
            },
            "priority": {
                "title": "Co by vás nejvíc naštvalo na špatně vybraném autě?",
                "options": {
                    "cost": "Vysoké náklady na provoz",
                    "repairs": "Časté opravy",
                    "power": "Nedostatek síly/výkonu",
                    "comfort": "Nepohodlí na dlouhých cestách",
                },
            },
        },
    },
    "results": {
        "title": {
            "one": "{count} shoda pro vás",
            "few": "{count} shody pro vás",
            "other": "{count} shod pro vás",
        },
        "browsingTitle": {
            "one": "{count} vůz v katalogu",
            "few": "{count} vozy v katalogu",
            "other": "{count} vozů v katalogu",
        },
        "updated": "Aktualizováno podle vaší poslední zprávy",
        "startPrompt": "Začněte konverzaci a AI vám katalog zúží podle vašich potřeb.",
        "emptyState": "Zatím nic nevyhovuje vašim požadavkům — zkuste je v konverzaci upravit.",
        "loadingMore": "Načítám další…",
        "loadingCatalog": "Načítám katalog…",
        "catalogError": "Nepodařilo se načíst katalog vozů.",
        "sortBy": "Seřadit podle",
        "sort": {
            "recommended": "Doporučeno",
            "price_asc": "Cena: od nejnižší",
            "price_desc": "Cena: od nejvyšší",
            "alpha": "Abecedně",
            "custom": "Moje pořadí",
        },
        "dragHint": "Přetáhněte pro změnu pořadí",
        "filters": {
            "all": "Vše",
            "brand": "Výrobce",
            "fuelType": "Druh motoru",
            "drivetrain": "Pohon",
        },
    },
    "car": {
        "photoPlaceholder": "fotka auta — {make} {model}",
        "topMatch": "Nejlepší shoda",
    },
    "requirements": {
        "subtitle": "Běžný jazyk, převedený na technické specifikace.",
        "empty": "Zatím nebyly zachyceny žádné požadavky.",
    },
    "vehicleDetail": {
        "close": "Zavřít",
        "loading": "Načítám detail vozu…",
        "error": "Nepodařilo se načíst detail vozu.",
        "sections": {
            "powertrain": "Motor a pohon",
            "colors": "Barvy",
            "standardEquipment": "Standardní výbava",
            "optionalEquipment": "Volitelná výbava",
            "priceHistory": "Historie ceny",
        },
        "fields": {
            "fuelType": "Palivo",
            "transmission": "Převodovka",
            "drivetrain": "Pohon",
            "power": "Výkon",
            "consumption": "Spotřeba",
            "co2": "Emise CO₂",
            "noData": "Údaj není k dispozici",
        },
        "priceHistory": {
            "current": "aktuální",
            "lowestPrice30d": "nejnižší cena za 30 dní: {price}",
        },
        "noColors": "Žádné barevné varianty nejsou k dispozici.",
        "noOptionalEquipment": "Žádná volitelná výbava není k dispozici.",
        "enums": {
            "fuelType": {
                "petrol": "Benzín",
                "diesel": "Nafta",
                "hybrid": "Hybrid",
                "mild_hybrid": "Mild hybrid",
                "phev": "Plug-in hybrid",
                "electric": "Elektromobil",
            },
            "drivetrain": {
                "fwd": "Pohon předních kol",
                "rwd": "Pohon zadních kol",
                "awd": "Pohon všech kol (4×4)",
            },
            "consumptionUnit": {
                "l_100km": "l/100 km",
                "kwh_100km": "kWh/100 km",
            },
            "colorFinish": {
                "solid": "Uni",
                "metallic": "Metalíza",
                "pearlescent": "Perleťová",
            },
            "optionCategory": {
                "equipment": "Výbava",
                "package": "Balíček",
                "warranty": "Záruka",
                "service": "Servis",
            },
        },
    },
}


def t(path: str, **kwargs: object) -> str:
    """Looks up one string by dotted path and formats it.

    Args:
        path: Dotted key path into `STRINGS`, e.g. `"chat.send"` or
            `"vehicleDetail.enums.fuelType.petrol"`.
        **kwargs: Values to interpolate into the string via `str.format`,
            e.g. `t("car.photoPlaceholder", make="Mazda", model="CX-5")`.

    Returns:
        The formatted string.

    Raises:
        KeyError: `path` doesn't resolve to a string in `STRINGS`.
    """
    node: object = STRINGS
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(f"No i18n string at {path!r}")
        node = node[part]
    if not isinstance(node, str):
        raise KeyError(f"{path!r} is not a leaf string")
    return node.format(**kwargs) if kwargs else node


def plural_key(count: int) -> str:
    """Picks the Czech plural form key for a count.

    Czech distinguishes exactly three forms for this kind of count: 1 (`one`),
    2-4 (`few`), and 0 or 5+ (`other`) - the fourth i18next form (`many`, for
    fractional counts) never applies here since these are always integer
    item counts.

    Args:
        count: The number being displayed (e.g. a result count).

    Returns:
        `"one"`, `"few"`, or `"other"` - a key under `results.title`/
        `results.browsingTitle` in `STRINGS`.
    """
    if count == 1:
        return "one"
    if 2 <= count <= 4:
        return "few"
    return "other"


def t_count(path: str, count: int) -> str:
    """Looks up a pluralized string (one with `one`/`few`/`other` sub-keys)
    and formats it with `count`.

    Args:
        path: Dotted path to the pluralized group, e.g. `"results.title"`.
        count: The count to pick a plural form for and interpolate.

    Returns:
        The formatted string for `count`'s plural form.
    """
    return t(f"{path}.{plural_key(count)}", count=count)
