"""UI copy and the lookup helpers over it. `STRINGS` below is the Czech
copy (ported verbatim from the former frontend's `src/i18n/locales/cs.json`);
`app/ui/i18n_en.py`'s `STRINGS_EN` is its key-for-key English translation.
No i18n library: plain nested dicts plus a small lookup/pluralization helper
are enough for two fixed languages and keep the UI layer dependency-free.

The language is chosen per browser by the header's toggle and remembered in
`app.storage.user` (see `current_language`/`set_language`); Czech is the
default. Prices stay in CZK in both languages - the catalog only covers the
Czech market.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from nicegui import app

from app.ui.i18n_en import STRINGS_EN

DEFAULT_LANGUAGE = "cs"
LANGUAGE_STORAGE_KEY = "language"

# Set by `use_language` - for code that runs where `app.storage.user` can't
# be read (a `run.io_bound` worker thread, a test), so it has to be told
# the language explicitly instead.
_language_override: ContextVar[str | None] = ContextVar("ui_language_override", default=None)

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
        "account": "Účet",
        "admin": "Admin",
        "articles": "Články",
        "myArticles": "Moje články",
        "becomeAuthor": "Stát se autorem",
        "sendFeedback": "Napsat zpětnou vazbu",
        # Named in the language it switches TO, so it's recognizable to
        # someone who can't read the current one.
        "switchLanguage": "English",
    },
    "common": {
        # strftime pattern for dates shown to the user (share links, PDF).
        "dateFormat": "%d. %m. %Y",
    },
    "admin": {
        "title": "Rovis — Admin",
        "sources": "Zdroje (config/sources.yaml)",
        "active": "aktivní",
        "inactive": "neaktivní",
        "run": "Spustit",
        "running": "Běží…",
        "done": "Hotovo",
        "failed": "Chyba (kód {code})",
        "progress": {
            "starting": "Spouštím…",
            "step": "{step} / {steps} · {item}",
            "sub": "({sub} / {subs})",
            "elapsed": "Běží {elapsed}",
            "remaining": "zbývá asi {remaining}",
            "lastRun": "Poslední úspěšný běh trval {duration}",
        },
        "jobs": {
            "scraper": {
                "title": "1. Spustit scraper",
                "description": (
                    "Stáhne a zpracuje nové ceníky ze všech aktivních zdrojů do storage/scraper.db. "
                    "Samo o sobě nemění katalog, který appka zobrazuje - k tomu slouží krok níže."
                ),
            },
            "import": {
                "title": "2. Naimportovat do katalogu",
                "description": (
                    "Přenese nově zparsovaná data ze storage/scraper.db do katalogu (storage/drivewise.db) "
                    "- teprve po tomto kroku se nové/aktualizované vozy objeví v appce. Bezpečné spouštět "
                    "opakovaně."
                ),
            },
        },
        "tabs": {
            "data": "Data",
            "controls": "Ovládání",
            "aiTrace": "AI komunikace",
            "authors": "Autoři",
            "feedback": "Zpětná vazba",
            "feedbackNew": "Zpětná vazba ({count})",
        },
        "trace": {
            "title": "Komunikace s AI ({provider})",
            "description": (
                "Kompletní záznam každého volání AI API — přesně odeslaný požadavek, celá odpověď "
                "nebo chyba, tokeny a doba trvání. Drží se jen v paměti serveru (posledních {max} "
                "volání), po restartu zmizí. Obsahuje texty, které uživatelé napsali do chatu."
            ),
            "disabled": "Záznam je vypnutý (LLM_TRACE_MAX_ENTRIES=0).",
            "summary": "{count} volání · {errors} chyb · {tokens} tokenů",
            "autoRefresh": "Živě obnovovat",
            "refresh": "Obnovit",
            "clear": "Vymazat",
            "empty": "Zatím žádné volání. Napište něco do chatu v appce a záznam se tu objeví.",
            "ok": "OK",
            "failed": "Chyba: {code}",
            "tokens": "{input} → {output} tokenů",
            "noUsage": "tokeny neuvedeny",
            "request": "Požadavek",
            "reply": "Odpověď (text)",
            "error": "Chyba",
            "rawRequest": "Surový požadavek (JSON)",
            "rawResponse": "Surová odpověď (JSON)",
            "emptyReply": "(prázdná odpověď)",
            "purposes": {
                "requirement_extraction": "Extrakce požadavků",
                "explanation": "Vysvětlení doporučení",
                "unknown": "Neurčeno",
            },
        },
    },
    "authors": {
        "request": {
            "title": "Stát se autorem",
            "description": (
                "Autoři mohou na portálu Rovis psát a zveřejňovat články - všem nebo jen vybraným "
                "uživatelům. Žádost posoudí administrátor."
            ),
            "nameLabel": "Jméno, pod kterým budete publikovat",
            "messageLabel": "Vzkaz pro administrátora (nepovinné)",
            "submit": "Odeslat žádost",
            "sending": "Odesílám…",
            "close": "Zavřít",
            "pending": "Vaše žádost z {date} čeká na schválení administrátorem.",
            "sent": "Žádost odeslána. Jakmile ji administrátor schválí, najdete v menu účtu „Moje články“.",
            "rejected": "Vaše předchozí žádost z {date} byla zamítnuta. Můžete poslat novou.",
        },
        "admin": {
            "pendingTitle": "Žádosti o roli autora",
            "noPending": "Žádné čekající žádosti.",
            "requested": "Požádal(a) {date}",
            "approve": "Schválit",
            "reject": "Zamítnout",
            "authorsTitle": "Autoři",
            "noAuthors": "Zatím žádní autoři.",
            "articleCount": "Článků: {count}",
            "revoke": "Odebrat roli",
            "approved": "Role autora přidělena: {email}",
            "rejectedNote": "Žádost zamítnuta: {email}",
            "revoked": "Role autora odebrána: {email}",
        },
        "errors": {
            "invalid_name": "Vyplňte prosím jméno (nejvýše 120 znaků).",
            "message_too_long": "Vzkaz je příliš dlouhý (nejvýše 2000 znaků).",
            "already_author": "Roli autora už máte.",
            "already_pending": "Vaše žádost už čeká na schválení.",
            "forbidden": "Na tuto akci nemáte oprávnění.",
            "not_found": "Žádost ani uživatel nebyli nalezeni.",
            "already_decided": "O žádosti už bylo rozhodnuto.",
            "unknown_error": "Něco se nepovedlo. Zkuste to prosím znovu.",
        },
    },
    "feedback": {
        "dialog": {
            "title": "Napsat zpětnou vazbu",
            "description": (
                "Narazili jste na chybu, máte nápad na vylepšení, nebo vás něco potěšilo? "
                "Napište nám - zprávu si přečte administrátor."
            ),
            "textLabel": "Vaše zpráva",
            "textPlaceholder": "Co se stalo, co byste chtěli, nebo co se vám líbí…",
            "attachRequirements": "Přiložit moje aktuální požadavky na auto",
            "contextNote": "Spolu se zprávou odešleme: verzi aplikace ({version}), jazyk a část aplikace ({page}).",
            "submit": "Odeslat",
            "sending": "Odesílám…",
            "close": "Zavřít",
            "sent": "Děkujeme! Zprávu jsme dostali.",
        },
        "types": {"bug": "Chyba", "idea": "Nápad", "praise": "Pochvala", "other": "Jiné"},
        "statuses": {
            "new": "Nové",
            "in_progress": "Řeší se",
            "resolved": "Vyřešeno",
            "wont_fix": "Nebude se řešit",
            "duplicate": "Duplicita",
        },
        "pages": {"search": "výběr auta"},
        "admin": {
            "empty": "Žádná zpětná vazba.",
            "allTypes": "Všechny typy",
            "allStatuses": "Všechny stavy",
            "context": "Odesláno z: {page} · verze {version} · jazyk {language}",
            "requirements": "Přiložené požadavky",
            "note": "Interní poznámka",
            "save": "Uložit",
            "saved": "Uloženo.",
        },
        "errors": {
            "empty_text": "Napište prosím zprávu.",
            "text_too_long": "Zpráva je příliš dlouhá (nejvýše 4000 znaků).",
            "note_too_long": "Poznámka je příliš dlouhá (nejvýše 4000 znaků).",
            "invalid_type": "Vyberte prosím, o co jde (chyba, nápad, pochvala, jiné).",
            "invalid_status": "Neplatný stav.",
            "rate_limited": "Dnes jste už poslali hodně zpráv. Zkuste to prosím zítra.",
            "forbidden": "Na tuto akci nemáte oprávnění.",
            "not_found": "Zpětná vazba nebyla nalezena.",
            "unknown_error": "Něco se nepovedlo. Zkuste to prosím znovu.",
        },
    },
    "articles": {
        "pageTitle": "Články — Rovis",
        "title": "Články",
        "empty": "Zatím tu nejsou žádné články.",
        "byline": "{author} · {date}",
        "editorial": "Redakce Rovis",
        "sharedWithYou": "Sdíleno s vámi",
        "notFound": "Článek neexistuje, nebo k němu nemáte přístup.",
        "notFoundHint": "Pokud vám ho někdo nasdílel, přihlaste se e-mailem, na který ho poslal.",
        "backToList": "← Všechny články",
        "backToApp": "← Zpět na výběr auta",
        "edit": "Upravit",
        "languages": {"cs": "Čeština", "en": "Angličtina"},
        # Shown when the reader's language version is missing - keyed by
        # the language the article IS available in.
        "onlyIn": {
            "cs": "Tento článek je zatím dostupný jen v češtině.",
            "en": "Tento článek je zatím dostupný jen v angličtině.",
        },
        "onlyInBadge": {"cs": "Jen česky", "en": "Jen anglicky"},
        # Named in the language it switches TO, like `header.switchLanguage`.
        "readIn": {"cs": "Číst česky", "en": "Read in English"},
        "visibility": {
            "label": "Kdo článek uvidí",
            "draft": "Jen já (koncept)",
            "restricted": "Vybraní uživatelé",
            "public": "Všichni",
        },
        "author": {
            "pageTitle": "Moje články — Rovis",
            "title": "Moje články",
            "new": "Nový článek",
            "empty": "Zatím jste nenapsal(a) žádný článek.",
            "updated": "Upraveno {date}",
            "onlyAuthors": "Tato stránka je jen pro autory.",
            "onlyAuthorsHint": "O roli autora můžete požádat v menu účtu na hlavní stránce („Stát se autorem“).",
            "backToMine": "← Moje články",
        },
        "editor": {
            "newTitle": "Nový článek",
            "editTitle": "Úprava článku",
            "titleLabel": "Nadpis",
            "placeholder": "Začněte psát…",
            "languagesHint": (
                "Článek můžete napsat česky, anglicky, nebo v obou jazycích. Stačí vyplnit jednu záložku - "
                "čtenáři druhého jazyka uvidí dostupnou verzi s upozorněním."
            ),
            "emptyVersion": "prázdné",
            "recipientsLabel": "E-maily čtenářů (oddělte čárkou nebo novým řádkem)",
            "recipientsHint": "Článek uvidí po přihlášení na tento e-mail - i ten, kdo zatím účet nemá.",
            "saveDraft": "Uložit koncept",
            "publish": "Publikovat",
            "saving": "Ukládám…",
            "saved": "Uloženo",
            "published": "Publikováno",
            "view": "Zobrazit",
            "delete": "Smazat",
            "confirmDelete": "Opravdu smazat článek „{title}“? Tuto akci nelze vrátit.",
            "cancel": "Zrušit",
            "deleted": "Článek smazán",
        },
        "errors": {
            "forbidden": "Na tuto akci nemáte oprávnění.",
            "not_found": "Článek neexistuje.",
            "empty_title": "Vyplňte prosím nadpis a text aspoň jedné jazykové verze.",
            "missing_title": "Doplňte prosím nadpis (verze: {detail}).",
            "title_too_long": "Nadpis je příliš dlouhý (nejvýše 200 znaků).",
            "content_too_long": "Článek je příliš dlouhý - zkuste zmenšit nebo odebrat vložené obrázky.",
            "invalid_recipient": "Neplatná e-mailová adresa: {detail}",
            "no_recipients": "Zadejte aspoň jeden e-mail čtenáře, nebo zvolte jinou viditelnost.",
            "too_many_recipients": "Příliš mnoho čtenářů (nejvýše 200).",
            "unknown_error": "Něco se nepovedlo. Zkuste to prosím znovu.",
        },
    },
    "mobileTabs": {
        "chat": "Konverzace",
        "results": "Výsledky",
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
        # Stands in for the user's chat bubble when a logged-in user's saved
        # requirements are restored (see app/ui/state.py).
        "restoreSummary": "Moje uložené požadavky z minulé relace.",
        "errors": {
            "ai_invalid_key": (
                "AI služba odmítla API klíč (neplatný nebo zrušený). "
                "Zadejte ho znovu přes „AI klíč“ v nabídce účtu vpravo nahoře."
            ),
            # Shown instead of ai_invalid_key to non-admins, who can't reach the
            # "AI klíč" menu item (admin-only) that message points at.
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
        # Lines recorded in the requirements' `notes` field (see
        # `WizardState.to_structured_requirements`).
        "notes": {
            "brandPref": "Preference značky: {value}",
            "annualKm": "Roční nájezd přibližně {km} km",
        },
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
        # Results title while the first catalog page is still loading -
        # instead of a misleading "0 vozů v katalogu".
        "loadingTitle": "Katalog vozů",
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
        "dragHintTouch": "Pořadí změníte přetažením karty za úchyt ⠿.",
        "controlsToggle": "Řazení a filtry",
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
        "like": "Líbí se mi — oblíbené modely mají přednost ve vyhledávání",
    },
    "compare": {
        "toggle": "Porovnat",
        "full": "Porovnat jde nejvýš {max} vozy. Nejdřív některý odeberte.",
        "trayTitle": "K porovnání",
        "trayCount": "K porovnání: {count}",
        "open": "Porovnat ({count})",
        "needTwo": "Vyberte aspoň 2 vozy.",
        "clear": "Vymazat",
        "remove": "Odebrat z porovnání",
        "title": "Porovnání vozů",
        "differencesOnly": "Zobrazit jen rozdíly",
        "bestHint": "Zvýrazněno = nejlepší hodnota v řádku",
        "loading": "Načítám porovnání…",
        "error": "Porovnání se nepodařilo načíst.",
        "tooFew": "K porovnání zbyl jen jeden vůz — přidejte další z výsledků.",
        "noDifferences": "V této části se vozy neliší.",
        "detail": "Detail",
        "standard": "✓ v ceně",
        "missing": "—",
        "colorSummary": "Barev: {count} · {range}",
        "perBrandNote": (
            "Každá značka pojmenovává výbavu jinak, proto ji u vozů různých značek ukazujeme pro každý vůz zvlášť."
        ),
        "standardCount": "Standardní výbava ({count})",
        "optionalCount": "Volitelná výbava ({count})",
        "add": "Přidat k porovnání",
        "added": "V porovnání",
        "compareTrims": "Porovnat výbavy",
        "sections": {
            "overview": "Přehled",
            "equipment": "Výbava",
        },
        "rows": {
            "price": "Cena",
            "matchScore": "Shoda",
            "colors": "Nabídka barev",
        },
        "trimPicker": {
            "title": "Které výbavy porovnat?",
            "hint": "Vyberte 2 až {max}. Předvybraná je vaše výbava a cenově nejbližší.",
            "sameEngine": "stejný motor",
            "otherEngine": "jiný motor (nejlevnější varianta)",
            "current": "vaše",
            "selected": "Vybráno {count} z {max}",
            "confirm": "Porovnat",
            "cancel": "Zrušit",
            "single": "Tento model je v katalogu jen v jedné výbavě.",
            "loading": "Načítám výbavy…",
        },
        "pdf": {
            "title": "Porovnání vozů",
        },
    },
    "requirements": {
        "subtitle": "Běžný jazyk, převedený na technické specifikace.",
        "empty": "Zatím nebyly zachyceny žádné požadavky.",
        "close": "Zavřít",
    },
    "share": {
        "button": "Sdílet",
        "creating": "Připravuji odkaz…",
        "error": "Odkaz se nepodařilo vytvořit. Zkuste to prosím znovu.",
        "title": "Sdílet výběr",
        "description": (
            "Kdokoli s tímto odkazem uvidí tento výběr, i bez účtu. Odkaz platí do {date} "
            "a neobsahuje vaše jméno ani e-mail."
        ),
        "copy": "Kopírovat odkaz",
        "copied": "Odkaz zkopírován",
        "native": "Sdílet…",
        "nativeTitle": "Výběr aut z Rovis",
        "qrHint": "Naskenujte telefonem, třeba v autosalonu.",
        "close": "Zavřít",
        "pageTitle": "Sdílený výběr aut · Rovis",
        "heading": {
            "one": "Sdílený výběr: {count} vůz",
            "few": "Sdílený výběr: {count} vozy",
            "other": "Sdílený výběr: {count} vozů",
        },
        "asOf": "Ceny k {created} · odkaz platí do {expires}",
        "requirements": "Požadavky",
        "priceNote": (
            "Ceny jsou z ceníků výrobců ke dni sdílení a mezitím se mohly změnit. "
            "Aktuální nabídku najdete v aplikaci nebo u prodejce."
        ),
        "findOwn": "Najít vlastní auto",
        "notFound": "Odkaz neexistuje nebo už vypršel.",
        "notFoundHint": "Sdílené odkazy platí omezenou dobu. Požádejte o nový, nebo si auto najděte sami.",
    },
    "vehicleDetail": {
        "close": "Zavřít",
        "exportPdf": "Stáhnout PDF",
        "exportPdfError": "PDF se nepodařilo vytvořit.",
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
        "units": {
            # Horsepower abbreviation, as in "110 kW (150 k)".
            "hp": "k",
        },
        "priceHistory": {
            "current": "aktuální",
            "lowestPrice30d": "nejnižší cena za 30 dní: {price}",
        },
        "pdf": {
            "created": "Vytvořeno {date}",
            "included": "v ceně",
            "page": "Strana {page}/{total}",
            "disclaimer": ("Údaje vycházejí z ceníků výrobců a mohou se změnit. Závaznou nabídku vám dá prodejce."),
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


LOCALES: dict[str, dict] = {"cs": STRINGS, "en": STRINGS_EN}
LANGUAGES = tuple(LOCALES)


def current_language() -> str:
    """The language UI text should be rendered in right now.

    Returns:
        `use_language`'s override if one is active, else the language this
        browser picked (`app.storage.user`), else `DEFAULT_LANGUAGE` -
        including outside any UI context (no request to read storage from).
    """
    override = _language_override.get()
    if override is not None:
        return override
    try:
        language = app.storage.user.get(LANGUAGE_STORAGE_KEY)
    except (RuntimeError, AssertionError, KeyError):
        return DEFAULT_LANGUAGE
    return language if language in LOCALES else DEFAULT_LANGUAGE


def set_language(language: str) -> None:
    """Remembers `language` for this browser (all its tabs, across reloads).

    Args:
        language: One of `LANGUAGES`.

    Raises:
        ValueError: `language` isn't one of `LANGUAGES`.
    """
    if language not in LOCALES:
        raise ValueError(f"Unsupported language {language!r}")
    app.storage.user[LANGUAGE_STORAGE_KEY] = language


@contextmanager
def use_language(language: str) -> Iterator[None]:
    """Makes `t()` render in `language` inside the `with` block, whatever
    the browser picked - e.g. inside a `run.io_bound` worker thread, which
    has no UI context to read the browser's choice from.

    Args:
        language: One of `LANGUAGES`.
    """
    token = _language_override.set(language)
    try:
        yield
    finally:
        _language_override.reset(token)


def t(path: str, *, lang: str | None = None, **kwargs: object) -> str:
    """Looks up one string by dotted path and formats it.

    Args:
        path: Dotted key path into the locale dict, e.g. `"chat.send"` or
            `"vehicleDetail.enums.fuelType.petrol"`.
        lang: Language to use; `None` (the default) means
            `current_language()`.
        **kwargs: Values to interpolate into the string via `str.format`,
            e.g. `t("car.photoPlaceholder", make="Mazda", model="CX-5")`.

    Returns:
        The formatted string.

    Raises:
        KeyError: `path` doesn't resolve to a string in the locale.
    """
    node: object = LOCALES.get(lang or current_language(), STRINGS)
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(f"No i18n string at {path!r}")
        node = node[part]
    if not isinstance(node, str):
        raise KeyError(f"{path!r} is not a leaf string")
    return node.format(**kwargs) if kwargs else node


def plural_key(count: int, lang: str = DEFAULT_LANGUAGE) -> str:
    """Picks the plural form key for a count.

    Czech distinguishes exactly three forms for this kind of count: 1 (`one`),
    2-4 (`few`), and 0 or 5+ (`other`) - the fourth i18next form (`many`, for
    fractional counts) never applies here since these are always integer
    item counts. English only has `one` and `other`.

    Args:
        count: The number being displayed (e.g. a result count).
        lang: Language whose plural rules apply.

    Returns:
        `"one"`, `"few"` (Czech only), or `"other"` - a key under
        `results.title`/`results.browsingTitle` in the locale dict.
    """
    if count == 1:
        return "one"
    if lang == "cs" and 2 <= count <= 4:
        return "few"
    return "other"


def t_count(path: str, count: int, *, lang: str | None = None) -> str:
    """Looks up a pluralized string (one with `one`/`few`/`other` sub-keys,
    or just `one`/`other` in English) and formats it with `count`.

    Args:
        path: Dotted path to the pluralized group, e.g. `"results.title"`.
        count: The count to pick a plural form for and interpolate.
        lang: Language to use; `None` means `current_language()`.

    Returns:
        The formatted string for `count`'s plural form.
    """
    language = lang or current_language()
    return t(f"{path}.{plural_key(count, language)}", lang=language, count=count)
