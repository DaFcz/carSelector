"""Demo catalog data: two real, hand-verified vehicles drawn from the price
lists in storage/cars/ - see backend/README.md's Tests section for how the
source figures were verified.

- Mazda CX-5 (storage/cars/mazda/cx-5/) - Prime-Line/Centre-Line trims,
  colors and per-trim equipment read from the brochure's own "NABÍDKA BAREV
  KAROSERIE" and VÝBAVA tables.
- Volkswagen Tiguan (storage/cars/vw/tiguan/) - People/R-Line People trims,
  paint codes read from the brochure's "Barvy" page, optional equipment
  (with real surcharges) from its "Příplatková výbava" pages.

`seed_demo_data()` is the single source of truth for this dataset, shared by:
- tests/conftest.py's `seeded_session` fixture (in-memory SQLite, per test)
- `python -m app.db.seed` (this module's __main__ block, against whatever
  DATABASE_URL points at - the persistent SQLite file by default)

Core entities (brand/model/trim/powertrain/configuration/source_document/
price) get explicit ids so tests can cross-reference specific configurations
deterministically (e.g. `config_prime_2wd_id`). Per-item rows (colors,
option items, their availabilities) are numerous and never individually
referenced, so those are left to autoincrement instead of hand-numbering
each one - still fully deterministic given a fixed insert order, just not
manually authored.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Brand,
    CarModel,
    Color,
    Configuration,
    ConfigurationColor,
    OptionAvailability,
    OptionItem,
    Powertrain,
    Price,
    SourceDocument,
    Trim,
)
from app.models.enums import (
    AvailabilityStatus,
    ColorFinish,
    Drivetrain,
    DocumentType,
    FuelType,
    OptionCategory,
)


@dataclass
class SeededData:
    model_id: int
    config_prime_2wd_id: int
    config_centre_awd_id: int
    vw_model_id: int
    config_people_fwd_id: int
    config_rline_awd_id: int


def _add_standard_equipment(
    session: Session,
    model_id: int,
    items: list[tuple[str, str]],
    *,
    all_configuration_ids: list[int],
    mark_to_configuration_id: dict[str, int],
) -> None:
    """Creates one `OptionItem` per `(name, mark)` row plus a `standard`
    `OptionAvailability` for whichever configuration(s) that mark means.

    No surcharge is ever set here - by construction every row created is
    `standard`, and `option_availability`'s CHECK constraint requires
    `surcharge_amount` to be null for anything that isn't `optional`.

    Args:
        session: Session to add the new rows to (not flushed/committed).
        model_id: `option_items.model_id` for every item this call creates.
        items: `(name, mark)` pairs. `mark` is either `"B"` (standard on
            every id in `all_configuration_ids`) or a key into
            `mark_to_configuration_id` for a single configuration.
        all_configuration_ids: Every configuration id `"B"` should apply to.
        mark_to_configuration_id: Maps a single-configuration mark (e.g.
            `"P"`, `"C"`, `"R"`) to the configuration id it means standard
            on.
    """
    for name, mark in items:
        option = OptionItem(model_id=model_id, category=OptionCategory.equipment, name=name)
        session.add(option)
        session.flush()
        target_ids = all_configuration_ids if mark == "B" else [mark_to_configuration_id[mark]]
        for configuration_id in target_ids:
            session.add(
                OptionAvailability(
                    option_item_id=option.id,
                    configuration_id=configuration_id,
                    availability=AvailabilityStatus.standard,
                )
            )


def _add_optional_equipment(
    session: Session,
    model_id: int,
    items: list[tuple[str, str | None, OptionCategory, float]],
    configuration_ids: list[int],
    *,
    currency: str = "CZK",
) -> None:
    """Creates one `OptionItem` per `(name, code, category, surcharge)` row
    plus an `optional` `OptionAvailability` (with that surcharge) for every
    id in `configuration_ids`.

    Args:
        session: Session to add the new rows to (not flushed/committed).
        model_id: `option_items.model_id` for every item this call creates.
        items: `(name, manufacturer_code, category, surcharge_amount)`
            tuples - `surcharge_amount` in `currency`, `0` for a real,
            disclosed "no extra cost" option (still `optional`, just free -
            distinct from `standard`, which every configuration gets
            regardless).
        configuration_ids: Every configuration id this equipment is offered
            on.
        currency: Currency every surcharge is denominated in.
    """
    for name, code, category, surcharge in items:
        option = OptionItem(model_id=model_id, category=category, code=code, name=name)
        session.add(option)
        session.flush()
        for configuration_id in configuration_ids:
            session.add(
                OptionAvailability(
                    option_item_id=option.id,
                    configuration_id=configuration_id,
                    availability=AvailabilityStatus.optional,
                    surcharge_amount=surcharge,
                    currency=currency,
                )
            )


def _add_colors(
    session: Session,
    model_id: int,
    items: list[tuple[str, str | None, ColorFinish | None, float]],
    configuration_ids: list[int],
    *,
    currency: str = "CZK",
) -> None:
    """Creates one `Color` per `(name, code, finish, surcharge)` row plus a
    `ConfigurationColor` (with that surcharge) for every id in
    `configuration_ids`.

    Args:
        session: Session to add the new rows to (not flushed/committed).
        model_id: `colors.model_id` for every color this call creates.
        items: `(name, manufacturer_code, finish_type, surcharge_amount)`
            tuples - `surcharge_amount` in `currency`, `0` for a
            no-extra-cost color (a color is always available once linked
            via `ConfigurationColor`, just sometimes free).
        configuration_ids: Every configuration id this color is offered on.
        currency: Currency every surcharge is denominated in.
    """
    for name, code, finish, surcharge in items:
        color = Color(model_id=model_id, name=name, manufacturer_code=code, finish_type=finish)
        session.add(color)
        session.flush()
        for configuration_id in configuration_ids:
            session.add(
                ConfigurationColor(
                    configuration_id=configuration_id,
                    color_id=color.id,
                    surcharge_amount=surcharge,
                    currency=currency,
                )
            )


# "NABÍDKA BAREV KAROSERIE" (page 10) - a flat list, no solid/metallic/
# pearlescent labeling given, unlike VW's categorized list below.
_MAZDA_COLORS: list[tuple[str, str | None, ColorFinish | None, float]] = [
    ("Arctic White", None, None, 0),
    ("Soul Crystal Red", None, None, 22_300),
    ("Machine Grey", None, None, 18_400),
    ("Rhodium White", None, None, 18_400),
    ("Aero Grey", None, None, 14_900),
    ("Polymetal Grey", None, None, 14_900),
    ("Jet Black", None, None, 14_900),
]

# VÝBAVA tables (pages 13-17), columns Prime-Line/Centre-Line/Exclusive-Line/
# Homura ("l"=standard, "–"=unavailable, "m"=optional-within-a-package with
# no standalone price given). Only Prime-Line ("P") and Centre-Line ("C") are
# seeded as configurations, so rows that are "–"/"m" on both those columns
# are left out entirely (nothing to attach them to; "m" rows also have no
# surcharge to satisfy option_availability's CHECK constraint - never
# fabricated here). "B" = standard on both.
_MAZDA_EQUIPMENT: dict[str, list[tuple[str, str]]] = {
    "Audio a infozábava": [
        ("8 reproduktorů", "B"),
        ("12,9” středový displej", "B"),
        ("Integrovaný Google", "B"),
        ("USB vpředu: 2× Typ C", "B"),
        ("Bluetooth", "B"),
        ("CarPlay a Android Auto", "P"),
        ("Bezdrátový CarPlay a Android Auto", "C"),
        ("AM/FM/DAB autorádio", "B"),
        ("Integrovaný navigační systém GPS (Mapy Google)", "B"),
        ("Bezdrátové nabíjení mobilního telefonu (Qi)", "C"),
    ],
    "Exteriér": [
        ("17” lité disky kol – Grey Metallic (225/65R17)", "P"),
        ("19” lité disky kol – černě frézované (225/55R19)", "C"),
        ("Přední LED světlomety s automatickým naklápěním", "B"),
        ("LED světla pro denní svícení", "B"),
        ("Přední a zadní spodní nárazník – černý", "B"),
        ("Podběhy kol – černé", "B"),
        ("Přední mřížka – černá", "B"),
        ("Charakteristické křídlo – šedé", "B"),
        ("Kryt zadního nárazníku – černý", "B"),
        ("Střešní ližiny – Black Gloss", "C"),
        ("Kryt sloupků B a C – Black Gloss", "B"),
        ("Zpětná zrcátka – Black Gloss", "B"),
        ("Lišty kolem oken – černé", "B"),
        ("Skla zadních bočních oken – zeleně tónovaná (UV ochrana)", "P"),
        ("Skla zadních bočních oken – tmavě tónovaná", "C"),
    ],
    "Interiér": [
        ("Sedadla potažená černou textilií", "P"),
        ("Černá umělá kůže a umělá kůže imitující semiš", "C"),
        ("Kůží potažený volant a hlavice řadicí páky", "B"),
        ("Kryt zavazadlového prostoru", "B"),
        ("Osvětlený vstup", "B"),
        ("Stropní konzole s držákem slunečních brýlí", "B"),
        ("Černé obložení dveří (dekor Gunmetal)", "B"),
        ("Vnitřní kliky dveří – Bright", "B"),
        ("Panel řazení – matný černý", "B"),
        ("Kroužek řadicí páky – lesklý", "B"),
        ("Tvrdá boční výplň konzole – černá", "B"),
        ("10,25” LCD přístrojová obrazovka", "B"),
        ("Sedadlo spolujezdce nastavitelné v osmi směrech", "P"),
        ("Elektricky ovládané sedadlo řidiče (10 směrů)", "C"),
        ("Nastavitelné sedadlo spolujezdce (šest směrů)", "B"),
        ("Elektricky ovládaná okna vpředu a vzadu", "B"),
        ("Zadní sedadlo: dělení 4:2:4", "B"),
        ("Víko přední konzoly – černé", "B"),
        ("Víko přední konzoly – černé nebo Pure White", "C"),
        ("Středová loketní opěrka s držákem na nápoje", "B"),
        ("ISO-FIX (2. řada, vnější sedadla)", "B"),
    ],
    "Bezpečnost": [
        ("Elektrická parkovací brzda (EPB) + Auto Hold", "B"),
        ("Automatický tempomat", "B"),
        ("Adaptivní tempomat Mazda (MRCC) se SLA", "B"),
        ("Asistenční systém pro bezpečný průjezd křižovatkou (CTS)", "B"),
        ("Pokročilý protikolizní systém (přední a zadní)", "B"),
        ("Systém upozornění na pohyb před vozem (FCTA)", "B"),
        ("Sledování provozu za vozidlem (RCTA)", "B"),
        ("Systém urgentního hlídání jízdních pruhů (ELK) s BSA", "B"),
        ("Nouzový asistenční systém (DEA)", "B"),
        ("Systém pro hlídání mrtvých úhlů (BSM)", "B"),
        ("Automatické přepínání potkávacích a dálkových světel (HBC)", "B"),
        ("Rozeznávání dopravních značek (TSR)", "B"),
        ("Inteligentní asistent pro hlídání rychlosti (ISA)", "B"),
        ("Hill Descent Control (HDC) – pouze s AWD", "C"),
        ("Proaktivní podpora řízení (DSA)", "B"),
        ("Systém pro hlídání pozornosti řidiče (DAA)", "B"),
        ("Systém monitorování řidiče (s kamerou)", "B"),
        ("Upozornění na otevření zadních dveří", "B"),
        ("Souprava na opravu pneumatik", "B"),
        ("Alarm s vnitřním pohybovým senzorem", "B"),
        ("Parkovací senzor (vpředu a vzadu)", "B"),
        ("Zadní kamera s dynamickými vodicími liniemi", "B"),
    ],
    "Pohodlí": [
        ("LED osvětlení přední části interiéru s bodovým světlem", "B"),
        ("LED osvětlení zadní části interiéru", "B"),
        ("Světelný a dešťový senzor", "B"),
        ("Zadní kapsa na sedadlech řidiče a spolujezdce", "C"),
        ("Vnitřní zpětné zrcátko bez rámečku", "C"),
        ("Sluneční clona s kosmetickým zrcátkem", "B"),
        ("Head-up displej", "C"),
        ("Mi-Drive – režimy Normal a Sport", "B"),
        ("Mi-Drive – režim Off-Road (jen s AWD)", "C"),
        ("Elektricky nastavitelná zpětná zrcátka", "B"),
        ("Vnitřní zpětné zrcátko s automatickým ztmavením", "C"),
        ("Dvouzónová automatická klimatizace", "B"),
        ("Výdechy ventilace pro zadní sedadla", "C"),
        ("Centrální zamykání s dálkovým ovládáním", "P"),
        ("Bezklíčové zamykání Smart Card", "C"),
        ("Palubní počítač s upozorněním na překročení rychlosti", "B"),
        ("Elektrické zamykání dveří", "B"),
        ("Automatické zamykání dveří", "B"),
        ("Vyhřívaná zpětná zrcátka", "C"),
        ("Vyhřívaný volant", "C"),
        ("Vyhřívaná přední sedadla", "C"),
        ("Paměť jízdní polohy", "C"),
        ("Zpětná zrcátka s manuálním sklápěním", "P"),
        ("Zpětná zrcátka s elektrickým a automatickým sklápěním", "C"),
        ("Odmrazovač stěračů", "C"),
        ("Elektricky ovládané zadní výklopné dveře", "C"),
        ("12V zásuvka (vpředu a v zavazadlovém prostoru)", "B"),
        ("LED osvětlení zavazadlového prostoru", "B"),
        ("Osvětlení kosmetického zrcátka", "C"),
    ],
}

# "Tiguan Barvy" (page 14): "Základní laky"/"Metalické laky"/"Laky s
# perleťovým efektem" map 1:1 onto ColorFinish. No per-trim restriction is
# legible in the source table (the People/People/R-Line checkbox column
# uses icon glyphs pdfplumber doesn't extract as text), so every color is
# offered on both seeded configurations.
_VW_COLORS: list[tuple[str, str | None, ColorFinish | None, float]] = [
    ("Bílá Pure", "0Q0Q", ColorFinish.solid, 0),
    ("Černá Grenadilla metalíza", "0E0E", ColorFinish.metallic, 0),
    ("Červená Persimon metalíza", "D3D3", ColorFinish.metallic, 4_000),
    ("Modrá Nightshade metalíza", "V2V2", ColorFinish.metallic, 0),
    ("Stříbrná Oyster metalíza", "F0F0", ColorFinish.metallic, 0),
    ("Šedá Dolphin metalíza", "B0B0", ColorFinish.metallic, 0),
    ("Zelená Cipressino metalíza", "D4D4", ColorFinish.metallic, 4_000),
    ("Bílá Oryx perleťový efekt", "0R0R", ColorFinish.pearlescent, 11_100),
]

# "Sériová výbava" (pages 3-6): pages 3-4 describe the People trim's
# standard equipment ("B" - R-Line People includes all of it too, since
# page 6 is headed "R-Line People navíc oproti výbavě People", i.e.
# R-Line's own page lists only what it adds ON TOP of People, "R" below).
# Items gated to powertrains outside the two seeded here (eHybrid/4MOTION-
# only lines on the People pages) are left out rather than misattributed.
_VW_STANDARD_EQUIPMENT: list[tuple[str, str]] = [
    ("Paket Design (zatmavená zadní okna, akustická skla, střešní nosiče)", "B"),
    ("Kryty vnějších zpětných zrcátek lakované v barvě karoserie", "B"),
    ("Bezpečnostní hlavové opěrky vpředu", "B"),
    ("Čelní airbagy u řidiče a spolujezdce", "B"),
    ("Čelní sklo tepelně izolující", "B"),
    ("Hlavové opěrky na zadních sedadlech (2 plnohodnotné)", "B"),
    ("Interiérový dekor Life", "B"),
    ("Komfortní sedadla vpředu s pneumaticky nastavitelnou bederní opěrkou", "B"),
    ("Loketní opěrka vpředu", "B"),
    ("ISOFIX", "B"),
    ("Make-up zrcátka ve slunečních clonách s osvětlením", "B"),
    ("Textilní koberečky vpředu a vzadu", "B"),
    ("Tříbodové bezpečnostní pásy s předepínači", "B"),
    ("Vnitřní zpětné zrcátko s automatickou clonou", "B"),
    ("Zcela sklopné opěradlo spolujezdce", "B"),
    ("Alarm s ostrahou interiéru", "B"),
    ("Asistent rozjezdu do kopce", "B"),
    ("Automatická 3zónová klimatizace", "B"),
    ("Bezklíčové odemykání a zamykání SAFELOCK", "B"),
    ("Bezpečnostní systém rozpoznávání chodců", "B"),
    ("Boční airbagy vpředu a vzadu se středovým airbagem", "B"),
    ("Elektromechanická parkovací brzda s funkcí Auto Hold", "B"),
    ("Dešťový senzor", "B"),
    ("Front Cross Traffic Alert (asistent vjezdu do křižovatky)", "B"),
    ("Keyless Start", "B"),
    ("Lane Assist", "B"),
    ("LED světlomety Plus s Light Assist", "B"),
    ("Rozpoznávání dopravních značek", "B"),
    ("Systém nouzového brzdění Front Assist", "B"),
    ("Parkovací senzory vpředu a vzadu s Park Assist Plus", "B"),
    ("Systém sledování únavy a pozornosti řidiče", "B"),
    ("Side Assist a Rear Traffic Alert", "B"),
    ("Systém proaktivní ochrany cestujících PreCrash", "B"),
    ("Tísňové volání eCall", "B"),
    ("Vnější zpětná zrcátka elektricky sklopná a vyhřívaná, s pamětí", "B"),
    ("Zadní mlhové světlo", "B"),
    ("17” kola z lehké slitiny Venezia", "B"),
    ("Digital Cockpit Pro (úhlopříčka 10,25”)", "B"),
    ("Navigační systém Discover (dotykový displej 12,9”)", "B"),
    ("Bezdrátový App-Connect (Apple CarPlay, Android Auto)", "B"),
    ("Adaptivní regulace podvozku DCC Pro", "R"),
    ("Ambientní osvětlení interiéru R-Line (výběr z 30 barev)", "R"),
    ("Progresivní řízení", "R"),
    ("Paket IQ.DRIVE Premium (360° kamera Area View, Travel Assist, Emergency Assist)", "R"),
    ("IQ.LIGHT HD LED Matrix světlomety s Dynamic Light Assist", "R"),
    ("Head-up displej", "R"),
    ("Parkování na dálku pomocí telefonu Park Assist Pro", "R"),
    ("20” kola z lehké slitiny Leeds", "R"),
    ("Top sportovní sedadla vpředu ergoActive s masážní funkcí", "R"),
    ("Interiérový dekor R-Line", "R"),
]

# "Příplatková výbava" (pages 7-12) - real surcharges, so these can be
# `optional` (unlike Mazda's "m" rows above). Same per-trim caveat as
# _VW_COLORS: offered on both seeded configurations. Rows whose source text
# came back visibly OCR-garbled (reversed/interleaved characters from a
# rotated column header bleeding into the cell) are left out rather than
# guessed at - notably the tow-bar and bundled "Akční model" rows.
_VW_OPTIONAL_EQUIPMENT: list[tuple[str, str | None, OptionCategory, float]] = [
    ("Sound systém Harman/Kardon (10+1 reproduktorů, 700 W)", None, OptionCategory.equipment, 22_900),
    ("18” kola z lehké slitiny Bologna", "PJP", OptionCategory.equipment, 18_900),
    ("18” kola z lehké slitiny Napoli", "PJN", OptionCategory.equipment, 18_900),
    ("19” kola z lehké slitiny Catania", "PJQ", OptionCategory.equipment, 30_400),
    ("20” kola z lehké slitiny York", "PJU", OptionCategory.equipment, 0),
    ("20” kola z lehké slitiny York Black", "PJR", OptionCategory.equipment, 0),
    ("IQ.LIGHT HD LED Matrix světlomety", "PLB", OptionCategory.equipment, 17_300),
    ("Panoramatické střešní okno", "3FU", OptionCategory.equipment, 35_700),
    ("Paket Black Style", "WBQ", OptionCategory.package, 7_100),
    ("Paket Dark", "PS1", OptionCategory.package, 7_900),
    ("Potahy sedadel v kůži Varenna ergoActive", "PL5", OptionCategory.equipment, 62_700),
    ("Síť oddělující zavazadlový prostor", "3CX", OptionCategory.equipment, 5_400),
    ("Prodloužená záruka 5 let / 150 000 km", "EA9", OptionCategory.warranty, 6_300),
    ("Service – 5 let / 60 000 km", "$9A", OptionCategory.service, 31_900),
    ("Service – 5 let / 100 000 km", "$9B", OptionCategory.service, 42_800),
    ("Service – 5 let / 150 000 km", "$9C", OptionCategory.service, 73_100),
    ("Service Plus – 5 let / 60 000 km", "$9M", OptionCategory.service, 46_000),
    ("Service Plus – 5 let / 100 000 km", "$9N", OptionCategory.service, 78_800),
    ("Service Plus – 5 let / 150 000 km", "$9O", OptionCategory.service, 136_500),
]


def _seed_mazda_cx5(session: Session) -> tuple[int, int, int]:
    """Args:
        session: Session to add the Mazda CX-5 catalog rows to.

    Returns:
        `(model_id, config_prime_2wd_id, config_centre_awd_id)`.
    """
    brand = Brand(id=1, slug="mazda", name="Mazda")
    session.add(brand)
    session.flush()

    model = CarModel(id=1, brand_id=brand.id, slug="cx-5", name="CX-5", category="SUV", model_year=2026)
    session.add(model)
    session.flush()

    prime_line = Trim(id=1, model_id=model.id, name="Prime-Line", display_order=1)
    centre_line = Trim(id=2, model_id=model.id, name="Centre-Line", display_order=2)
    session.add_all([prime_line, centre_line])
    session.flush()

    engine_2wd = Powertrain(
        id=1,
        model_id=model.id,
        fuel_type=FuelType.petrol,
        transmission="6-speed automatic",
        drivetrain=Drivetrain.fwd,
        power_kw=104,
        power_hp=141,
        consumption_min=7.0,
        consumption_max=7.0,
        consumption_unit="l_100km",
        co2_min_g_km=157,
        co2_max_g_km=159,
    )
    engine_awd = Powertrain(
        id=2,
        model_id=model.id,
        fuel_type=FuelType.petrol,
        transmission="6-speed automatic",
        drivetrain=Drivetrain.awd,
        power_kw=104,
        power_hp=141,
        consumption_min=7.4,
        consumption_max=7.5,
        consumption_unit="l_100km",
        co2_min_g_km=168,
        co2_max_g_km=169,
    )
    session.add_all([engine_2wd, engine_awd])
    session.flush()

    config_prime_2wd = Configuration(id=1, trim_id=prime_line.id, powertrain_id=engine_2wd.id)
    config_centre_awd = Configuration(id=2, trim_id=centre_line.id, powertrain_id=engine_awd.id)
    session.add_all([config_prime_2wd, config_centre_awd])
    session.flush()

    all_config_ids = [config_prime_2wd.id, config_centre_awd.id]
    _add_colors(session, model.id, _MAZDA_COLORS, all_config_ids)
    for items in _MAZDA_EQUIPMENT.values():
        _add_standard_equipment(
            session,
            model.id,
            items,
            all_configuration_ids=all_config_ids,
            mark_to_configuration_id={"P": config_prime_2wd.id, "C": config_centre_awd.id},
        )

    source_doc = SourceDocument(
        id=1,
        model_id=model.id,
        file_path="storage/cars/mazda/cx-5/mazda_cx-5_akcni_cenik_2026-07_cz.pdf",
        document_type=DocumentType.price_list,
        market="CZ",
        locale="cs-CZ",
        effective_date=date(2025, 9, 22),
        campaign_valid_from=date(2026, 7, 1),
        campaign_valid_to=date(2026, 9, 30),
        retrieved_at=datetime.now(timezone.utc),
    )
    session.add(source_doc)
    session.flush()

    session.add_all(
        [
            Price(
                id=1,
                configuration_id=config_prime_2wd.id,
                source_document_id=source_doc.id,
                market="CZ",
                currency="CZK",
                list_price=875_900,
                discount_amount=51_000,
                price_incl_vat=824_900,
                lowest_price_30d=875_900,
                valid_from=date(2026, 7, 1),
                valid_to=None,
                scraped_at=datetime.now(timezone.utc),
            ),
            Price(
                id=2,
                configuration_id=config_centre_awd.id,
                source_document_id=source_doc.id,
                market="CZ",
                currency="CZK",
                list_price=1_074_900,
                discount_amount=51_000,
                price_incl_vat=1_023_900,
                lowest_price_30d=1_074_900,
                valid_from=date(2026, 7, 1),
                valid_to=None,
                scraped_at=datetime.now(timezone.utc),
            ),
        ]
    )
    session.commit()

    return model.id, config_prime_2wd.id, config_centre_awd.id


def _seed_vw_tiguan(session: Session) -> tuple[int, int, int]:
    """Args:
        session: Session to add the VW Tiguan catalog rows to.

    Returns:
        `(model_id, config_people_fwd_id, config_rline_awd_id)`.
    """
    brand = Brand(id=2, slug="volkswagen", name="Volkswagen")
    session.add(brand)
    session.flush()

    model = CarModel(id=2, brand_id=brand.id, slug="tiguan", name="Tiguan", category="SUV", model_year=2026)
    session.add(model)
    session.flush()

    people = Trim(id=3, model_id=model.id, name="People", display_order=1)
    rline_people = Trim(id=4, model_id=model.id, name="R-Line People", display_order=2)
    session.add_all([people, rline_people])
    session.flush()

    # "Ceník" (page 2) + "Technické údaje" (pages 16-17): one FWD diesel and
    # one AWD petrol variant, mirroring the Mazda sample's 2WD/AWD split.
    engine_tdi_fwd = Powertrain(
        id=3,
        model_id=model.id,
        manufacturer_code="CT1C4ZP2",
        fuel_type=FuelType.diesel,
        transmission="Automatická převodovka DSG7",
        drivetrain=Drivetrain.fwd,
        displacement_cc=1968,
        cylinder_count=4,
        power_kw=110,
        power_hp=150,
        top_speed_kmh=210,
        consumption_min=5.3,
        consumption_max=5.5,
        consumption_unit="l_100km",
        co2_min_g_km=140,
        co2_max_g_km=145,
        emission_standard="EU6",
    )
    engine_tsi_4motion = Powertrain(
        id=4,
        model_id=model.id,
        manufacturer_code="CT1EPTR2",
        fuel_type=FuelType.petrol,
        transmission="Automatická převodovka DSG7",
        drivetrain=Drivetrain.awd,
        displacement_cc=1984,
        cylinder_count=4,
        power_kw=150,
        power_hp=204,
        top_speed_kmh=228,
        consumption_min=7.7,
        consumption_max=7.7,
        consumption_unit="l_100km",
        co2_min_g_km=174,
        co2_max_g_km=174,
        emission_standard="EU6",
    )
    session.add_all([engine_tdi_fwd, engine_tsi_4motion])
    session.flush()

    config_people_fwd = Configuration(
        id=3, trim_id=people.id, powertrain_id=engine_tdi_fwd.id, manufacturer_code="CT1C4ZP2"
    )
    config_rline_awd = Configuration(
        id=4, trim_id=rline_people.id, powertrain_id=engine_tsi_4motion.id, manufacturer_code="CT1EPTR2"
    )
    session.add_all([config_people_fwd, config_rline_awd])
    session.flush()

    all_config_ids = [config_people_fwd.id, config_rline_awd.id]
    _add_colors(session, model.id, _VW_COLORS, all_config_ids)
    _add_standard_equipment(
        session,
        model.id,
        _VW_STANDARD_EQUIPMENT,
        all_configuration_ids=all_config_ids,
        mark_to_configuration_id={"R": config_rline_awd.id},
    )
    _add_optional_equipment(session, model.id, _VW_OPTIONAL_EQUIPMENT, all_config_ids)

    source_doc = SourceDocument(
        id=2,
        model_id=model.id,
        file_path="storage/cars/vw/tiguan/Akcni_Tiguan_People_01_07_2026_new_cover_new.pdf",
        document_type=DocumentType.price_list,
        market="CZ",
        locale="cs-CZ",
        effective_date=date(2027, 7, 1),
        retrieved_at=datetime.now(timezone.utc),
    )
    session.add(source_doc)
    session.flush()

    session.add_all(
        [
            Price(
                id=3,
                configuration_id=config_people_fwd.id,
                source_document_id=source_doc.id,
                market="CZ",
                currency="CZK",
                list_price=1_176_000,
                price_incl_vat=1_176_000,
                price_excl_vat=971_901,
                valid_from=date(2027, 7, 1),
                valid_to=None,
                scraped_at=datetime.now(timezone.utc),
            ),
            Price(
                id=4,
                configuration_id=config_rline_awd.id,
                source_document_id=source_doc.id,
                market="CZ",
                currency="CZK",
                list_price=1_459_000,
                price_incl_vat=1_459_000,
                price_excl_vat=1_205_785,
                valid_from=date(2027, 7, 1),
                valid_to=None,
                scraped_at=datetime.now(timezone.utc),
            ),
        ]
    )
    session.commit()

    return model.id, config_people_fwd.id, config_rline_awd.id


def seed_demo_data(session: Session) -> SeededData:
    mazda_model_id, config_prime_2wd_id, config_centre_awd_id = _seed_mazda_cx5(session)
    vw_model_id, config_people_fwd_id, config_rline_awd_id = _seed_vw_tiguan(session)

    return SeededData(
        model_id=mazda_model_id,
        config_prime_2wd_id=config_prime_2wd_id,
        config_centre_awd_id=config_centre_awd_id,
        vw_model_id=vw_model_id,
        config_people_fwd_id=config_people_fwd_id,
        config_rline_awd_id=config_rline_awd_id,
    )


def main() -> None:
    """`python -m app.db.seed` - creates tables if missing (equivalent to
    `alembic upgrade head` for this single-migration schema) and seeds the
    demo catalog, unless the DB already has data (safe to re-run).
    """
    from app.db.base import Base
    from app.db.session import SessionLocal, engine

    Base.metadata.create_all(engine)

    session = SessionLocal()
    try:
        if session.scalar(select(Brand.id).limit(1)) is not None:
            print("Database already has catalog data - skipping seed. "
                  "Delete drivewise.db (or point DATABASE_URL elsewhere) to reseed.")
            return
        data = seed_demo_data(session)
        print(
            f"Seeded 2 brands / 2 models / 4 configurations "
            f"(mazda model_id={data.model_id}, configuration_ids="
            f"{data.config_prime_2wd_id},{data.config_centre_awd_id}; "
            f"vw model_id={data.vw_model_id}, configuration_ids="
            f"{data.config_people_fwd_id},{data.config_rline_awd_id}) into "
            f"{engine.url}"
        )
    finally:
        session.close()


if __name__ == "__main__":
    main()
