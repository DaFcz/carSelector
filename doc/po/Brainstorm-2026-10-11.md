# Car Selector — Brainstorming nových featur (2026-10-11)

Třetí kolo brainstormingu, k verzi 0.3.6. Obsahuje **jen nové nápady**. Nic z toho se
neobjevilo v [Brainstorm-2026-09.md](./Brainstorm-2026-09.md),
[Brainstorm-2026-10-09.md](./Brainstorm-2026-10-09.md) (#1–#13 včetně zamítnutých),
[Feedback-proposal.md](./Feedback-proposal.md), [MVP.md](./MVP.md), [Version2.md](./Version2.md) ani v
[../ai/claude-integration-brainstorm.md](../ai/claude-integration-brainstorm.md). Kde nápad na
některý z nich navazuje, je to u něj uvedené. Číslování pokračuje od #14.

Odhad rozsahu: **S** = do dne, **M** = pár dní, **L** = týden a víc.

## Přehled

| # | Featura | Oblast | Rozsah | Závisí na |
|---|---|---|---|---|
| 14 | Režim „firemní auto“ (bez DPH, zdanění benefitu) | Rozhodování | M | — |
| 15 | „Zvládnu to s elektrem?“ (simulátor dojezdu) | Rozhodování | M | data o dojezdu/baterii |
| 16 | Graf vývoje ceny a „Teď, nebo počkat?“ | Data / rozhodování | S–M | historie cen (hotová) |
| 17 | Hlídací pes uloženého hledání | Retence | M | #8 Plánovaný scraping |
| 18 | Moje hledání (víc pojmenovaných hledání + historie) | Rozhodování | S–M | přihlášení (hotové) |
| 19 | Rychlé starty podle životní situace | Onboarding | S | — |
| 20 | Rodinný režim: požadavky víc lidí | AI | M–L | #18 |
| 21 | Checklist do autosalonu a na testovací jízdu | AI / výstup | S–M | PDF export (hotový) |
| 22 | Rozměry a „vejde se do garáže“ | Data / filtr | S–M | rozměry v datech |
| 23 | Bezpečnost Euro NCAP jako data a filtr | Data | M | zdroj dat |
| 24 | Poptávka u dealera a testovací jízda | Platforma / byznys | L | seznam dealerů |
| 25 | Skladové a předváděcí vozy | Data | L | zdroj dat od výrobců |
| 26 | Veřejné stránky modelů (SEO) | Platforma | M | — |
| 27 | Evaluační sada pro AI doporučení | Kvalita AI | M | — |

---

## 14. Režim „firemní auto“

**Co:** přepínač „Kupuju na firmu / jako OSVČ / služební auto zaměstnance“. Potom:

- ceny **bez DPH** všude (karty, detail, porovnání, PDF),
- u služebního auta **měsíční zdanění benefitu** pro zaměstnance podle typu pohonu (dnes
  1 % / 0,5 % pro nízkoemisní PHEV / 0,25 % pro BEV ze vstupní ceny; **před implementací
  ověřit aktuální znění**),
- řazení „podle měsíčního dopadu na výplatu“.

**Proč:** velká část nových aut v ČR se kupuje na firmu. Pro tyhle zákazníky je cena s DPH
nepřesná a rozdíl v benefitu mezi elektromobilem a spalovacím autem může rozhodnout. Žádný
existující návrh tuhle skupinu neřeší (TCO #2 počítá se soukromým kupcem).

**Návaznost:** výpočet patří do `app/services/` jako čistá funkce nad `Money`. Sazby a
podmínky (limit CO₂ pro PHEV) jsou v konfiguraci s platností od–do, protože se mění.
`StructuredRequirements` dostane pole `purchase_mode`, takže ho AI pozná i z věty „beru to
na IČO“. Ceníky výrobců často uvádějí cenu bez DPH přímo, ale spolehlivější je dopočítat ji.

**Rizika:** daňová oblast. Zobrazovat jako orientační odhad s odkazem na zdroj pravidla,
ne jako daňové poradenství.

## 15. „Zvládnu to s elektrem?“

**Co:** u elektromobilu a PHEV jednoduchý simulátor. Uživatel zadá své typické trasy
(denní dojíždění, cesta na chatu, dovolená) a jestli může nabíjet doma nebo v práci.
Výsledek pro každý vůz: „denní dojíždění zvládne ~5× na jedno nabití“, „na chatu
(180 km) v zimě s rezervou, zpátky nabíjet“, „k moři 1–2 nabíjecí zastávky“. Přepínač
léto/zima (v zimě se dojezd krátí).

**Proč:** obava z dojezdu je hlavní důvod, proč lidé elektromobil vůbec nezvažují.
Abstraktní „WLTP 450 km“ nic neříká. Konkrétní trasa uživatele ano. Otázka 6 v průvodci
([../ai/wizard-questions.md](../ai/wizard-questions.md)) už se na chování ptá, tohle je
odpověď, kterou z něj lze dát zpátky.

**Návaznost:** dojezd a kapacita baterie by měly být v `powertrains`. Pokud z ceníků
chybí, je to úkol pro scraper. Koeficienty (zima, dálnice) jsou konfigurace. Trasy jdou
vytáhnout z konverzace jako nové pole (`typical_trips`). Výsledek lze zobrazit i jako
řádek v porovnání (#1).

**Rizika:** nesmí to působit jako přesná navigace. Zobrazovat rozpětí a zdroj (WLTP)
a nepředstírat znalost nabíjecí sítě.

## 16. Graf vývoje ceny a „Teď, nebo počkat?“

**Co:** v detailu vozu malý graf ceny konfigurace v čase (z `prices` s platností) a
značky událostí: „akce od 1. 9.“, „nový ceník“, „zdražení o 2 %“. K tomu krátký
nehodnotící text: „Cena za posledních 6 měsíců klesla o 35 000 Kč, aktuální akce platí do
31. 10. (podle ceníku).“

**Proč:** append-only historie cen existuje, ale uživatel ji nevidí. Hlídač cen (#6)
upozorňuje *na změnu*. Tohle odpovídá na otázku *teď*: je to dobrá cena?

**Návaznost:** čistě čtecí dotaz nad `prices`, graf v NiceGUI (ECharts). Datum konce akce
jen tam, kde ho ceník uvádí (vazba na `source_documents`). Graf by šel přidat i do PDF.

**Rizika:** s málo daty (jeden ceník) graf nic neukáže. Zobrazit ho až od dvou cenových
bodů. Žádné předpovědi budoucí ceny.

## 17. Hlídací pes uloženého hledání

**Co:** „Dejte mi vědět, až bude v katalogu něco, co odpovídá tomuhle hledání.“ Uloží se
požadavky (ne konkrétní vůz) a po každém importu (#8) se znovu vyhodnotí. Když přibude
nová shoda (nový model, nová levnější výbava, která se nově vejde do rozpočtu), přijde
e-mail.

**Proč:** hlídač cen (#6) hlídá *oblíbený model*. Tenhle hlídá *potřebu*. Typicky „elektrické
SUV do 900 000 Kč“, které dnes neexistuje, ale může přibýt. Navazuje na „neuspokojené
dotazy“ z analytiky (#9): uživatel s 0 výsledky dostane místo slepé uličky tlačítko „Hlídat“.

**Návaznost:** `saved_requirements` už existuje (jedna sada na uživatele), přibude
tabulka hlídaných hledání, nebo se rozšíří #18. Vyhodnocení použije `RecommendationEngine`
bez LLM, takže je levné. E-mail přes `mailer.py` v jazyce uživatele, odhlášení jedním
kliknutím, souhrnný e-mail (stejné zásady jako #6).

## 18. Moje hledání

**Co:** přihlášený uživatel může mít víc pojmenovaných hledání („Auto pro mě“, „Druhé auto
pro manželku“, „Varianta s elektrem“), přepínat mezi nimi a vrátit se ke konverzaci,
ze které vzniklo.

**Proč:** dnes je uložená jen jedna sada požadavků a konverzace je jen v paměti (známá
mezera v [../implemented_overview.md](../implemented_overview.md)). Výběr auta trvá týdny
a lidé zkoušejí víc variant.

**Návaznost:** rozšíření `saved_requirements` o název a zpráv konverzace (ukládat jen u
přihlášených, s retencí a možností smazat). Výchozí bod pro #17 a #20. Sdílení „Pokračuj
odsud“ (#5 C) by pak mohlo vytvořit nové pojmenované hledání u příjemce.

**Rizika:** ukládání volného textu konverzací je osobní údaj. Uvést v zásadách a dát
tlačítko „Smazat historii“.

## 19. Rychlé starty podle životní situace

**Co:** na prázdné úvodní obrazovce 4–6 karet se situacemi: „Rodina, chata, horší cesty“,
„Do města, nabíjím doma“, „Hodně najezdím po dálnici“, „První auto, malý rozpočet“, „Tahám
přívěs / karavan“. Klik předvyplní požadavky a AI se doptá jen na rozpočet.

**Proč:** prázdné chatovací pole je pro netechnického uživatele bariéra. Karty ukážou, jak
se s aplikací mluví, a zkrátí cestu k prvnímu výsledku. Jsou to zároveň levné hledání,
protože požadavky jsou předvyplněné bez volání LLM.

**Návaznost:** karty jsou data (scénář → `StructuredRequirements`), ne kód. Lze je sdílet se
„scenario translation table“ z AI brainstormu jako few-shot příklady. Texty v `i18n.py`
i `i18n_en.py`. Analytika (#9) ukáže, které scénáře se používají.

## 20. Rodinný režim: požadavky víc lidí

**Co:** autor hledání pošle členům rodiny odkaz „Řekni, co od auta chceš“. Každý odpoví
krátce (svými slovy nebo přes průvodce). AI požadavky sloučí, ukáže **shody i konflikty**
(„Petr chce 4×4, Jana nechce nad 30 000 Kč ročně za provoz, 4×4 s naftou to zdražuje“)
a nabídne kompromisní shortlist.

**Proč:** o autě se rozhoduje v rodině (to byl důvod pro sdílení #5). Společný seznam
(#5 D) řeší hlasování *nad vozy*. Tohle řeší dřívější a těžší krok, dohodu *na požadavcích*.

**Návaznost:** odkaz bez nutnosti účtu (stejné zásady jako snapshot: náhodný token,
expirace, `noindex`). Odpovědi jako samostatné `StructuredRequirements` + slučovací krok
v `app/ai/` (nová schopnost přes `LlmClient`). Konflikty lze částečně určit bez LLM
(rozpočet min/max, pohon). Staví na #18.

**Rizika:** GDPR u odpovídajících bez účtu: neukládat jejich e-mail, jen odpovědi, a
smazat je s hledáním. Rozsah raději ověřit nejdřív jako „slučování dvou hledání“.

## 21. Checklist do autosalonu a na testovací jízdu

**Co:** u vybraného vozu (nebo porovnání) tlačítko „Připravit na návštěvu u dealera“.
Výsledkem je krátký osobní checklist:

- **co vyzkoušet** podle požadavků („s kočárkem: vyzkoušejte ho naložit do kufru“,
  „hodně dálnice: hluk při 130 km/h, adaptivní tempomat“),
- **na co se zeptat** („dodací lhůta“, „platí akce z ceníku z 1. 9.?“, „cena tažného
  zařízení podle ceníku 18 500 Kč“),
- **co v ceně není** (příplatková výbava, kterou uživatel chtěl).

Ke stažení jako PDF, s QR kódem na detail.

**Proč:** aplikace dnes končí u výběru, ale rozhoduje se v autosalonu. Checklist přenese
požadavky z aplikace do reálného rozhovoru a dá uživateli jistotu. Nejvíc tu pomáhá
kombinace AI a dat, které už máme.

**Návaznost:** generování v `app/ai/` ze stejného kontextu jako `explanation_generator`
(požadavky + data vozu), se stejnou disciplínou: konkrétní čísla jen z dat. PDF přes
existující export (0.2.40), QR přes #5 F.

## 22. Rozměry a „vejde se do garáže“

**Co:** vnější rozměry (délka, šířka se zrcátky, výška) jako data. Ve filtrech a v
konverzaci „mám garáž 4,7 × 2,4 m“ nebo „parkuju v úzké ulici“. Na kartě upozornění
„Do vaší garáže: s rezervou 20 cm“ / „nevejde se“.

**Proč:** častý tvrdý limit, na který lidé přijdou až v salonu. AI brainstorm navrhuje
odhad z fotky garáže. Tohle je levnější základ, na kterém by fotka později stavěla.

**Návaznost:** rozměry jsou v technických částech ceníků, scraper je dnes nečte. Pole do
`trims` nebo `specs` (podle [../db/db-structure.md](../db/db-structure.md)). Filtr v
`RecommendationEngine` jako tvrdé omezení jen tehdy, když uživatel rozměr opravdu zadá.

**Rizika:** šířka se zrcátky v ceníku často chybí. Bez údaje vůz nevyřazovat, jen ukázat
„rozměr neznámý“.

## 23. Bezpečnost Euro NCAP

**Co:** hvězdičky Euro NCAP (a rok testu) u modelu, filtr „jen 5 hvězd“ a priorita
„bezpečnost“ v doporučení. U rodin s dětmi i dílčí skóre ochrany dětí.

**Proč:** pro rodiny jeden z hlavních argumentů a objektivní, srovnatelný údaj napříč
značkami. Výbava se mezi značkami porovnává špatně (každá ji jinak pojmenovává), tohle
srovnat jde.

**Návaznost:** nová tabulka na úrovni modelu (rating, rok, dílčí skóre, odkaz na zdroj).
Plnit ručně v adminu nebo poloautomaticky. Priorita `safety` v `StructuredRequirements`
by konečně měla data, podle kterých skórovat.

**Rizika:** podmínky použití dat Euro NCAP ověřit předem. Hodnocení starší než 6 let
označit, protože metodika se mění.

## 24. Poptávka u dealera a testovací jízda

**Co:** v detailu vozu „Poptat u dealera“ / „Domluvit testovací jízdu“. Uživatel vybere
nejbližšího dealera (podle PSČ) a odešle poptávku s předvyplněnou konfigurací a cenou ze
snapshotu. Odesílá se až po jeho výslovném souhlasu, e-mail a telefon vyplní sám.

**Proč:** přirozený konec cesty uživatele a zároveň **první obchodní model** (poptávky pro
dealery), navazuje na úvahu „produkt pro dealery“ u analytiky (#9).

**Návaznost:** seznam dealerů po značkách (ruční správa v adminu, nebo z webů výrobců).
Odeslání přes `mailer.py` na adresu dealera, s rate-limitem. Snapshot (#5 A) slouží jako
„co přesně poptávám“.

**Rizika:** GDPR (souhlas se zpracováním, předání údajů třetí straně), riziko spamu a
dohody s dealery. Velká featura, smysl dává až u veřejné verze s uživateli.

## 25. Skladové a předváděcí vozy

**Co:** u modelu a konfigurace „Ihned k odběru: 3 vozy skladem, od 829 000 Kč“, s odkazem
na nabídku výrobce nebo dealera. Ve filtru „jen skladem / do 1 měsíce“.

**Proč:** dodací lhůta na objednávku je často měsíce a skladové vozy mají jinou cenu
(i slevu). Pro řadu lidí je „kdy to můžu mít“ stejně důležité jako cena.

**Návaznost:** někteří výrobci mají veřejné vyhledávače skladových vozů, každý jinak (nový
typ zdroje pro scraper vedle `pdf`/`json`/`html`). Data rychle stárnou, takže to vyžaduje
#8. Skladový vůz má konkrétní výbavu, nemapuje se tedy 1:1 na `configurations`. Nejspíš
samostatná tabulka s odkazem na model a nejbližší konfiguraci.

**Rizika:** podmínky použití webů výrobců, rychlé stárnutí dat a nejednotné formáty.
Začít jednou značkou jako proof of concept.

## 26. Veřejné stránky modelů (SEO)

**Co:** indexovatelné stránky `/modely/skoda/kodiaq`: přehled výbav a motorů, cenové
rozpětí, vývoj ceny (#16), související články (#10) a výrazné tlačítko „Hodí se mi? Zeptat
se AI“, které otevře chat s předvyplněným modelem.

**Proč:** dnes se na portál dá dostat jen přímo. Lidé hledají „Kodiaq cena 2026“ nebo
„Kodiaq vs Tiguan“. Stránky modelů a dvojic z nejčastějších porovnání (statistika
porovnání 0.3.6 ví, které dvojice to jsou) přivedou návštěvnost bez placené reklamy.

**Návaznost:** čtecí stránky nad katalogem, server-side render kvůli indexaci (ověřit, jak
dobře NiceGUI vrací obsah bez JavaScriptu, jinak jednoduchá šablona v FastAPI), sitemap,
`hreflang` pro CZ/EN. Žádná nová data.

**Rizika:** stránky s tenkým obsahem vyhledávače penalizují. Spouštět až s dostatkem
značek a článků.

## 27. Evaluační sada pro AI doporučení

**Co:** „zlatá“ sada 30–50 realistických zadání (česky i anglicky, včetně zadání ze
success scénáře v [../main.md](../main.md)) s očekávanými požadavky a tím, které vozy v
top N *musí* a *nesmí* být. Skript ji spustí proti aktuálnímu promptu a modelu a vypíše
skóre (přesnost extrakce polí, zásahy v top N, vymyšlené údaje ve vysvětleních).

**Proč:** AI vrstva se mění (prompty, poskytovatel Claude/Groq, modely), ale kvalitu dnes
nic neměří. 👍/👎 z feedbacku (varianta B) ukáže problém až u uživatelů. Evaluace ho ukáže
před nasazením. Je to i podklad pro rozhodnutí z #12, „který model na který účel“.

**Návaznost:** `scripts/eval_recommendations.py` + YAML se zadáními. Extrakce se testuje
proti `StructuredRequirements`, ranking proti zmrazenému katalogu (fixture), aby výsledky
nezávisely na importu. Běží ručně nebo v CI s vlastním klíčem a limitem nákladů. Případy
nahlášené přes 👎 se do sady přidávají jako regresní.

---

## Doporučené pořadí (jen nové nápady)

1. **#19 Rychlé starty** a **#16 Graf ceny**: malé, staví na hotových věcech a hned je
   uvidí každý uživatel.
2. **#27 Evaluační sada**: před dalšími AI featurami (#4 Chat k vozu, #20, #21), aby šlo
   měřit, jestli se kvalita nezhoršuje.
3. **#21 Checklist do autosalonu** a **#14 Firemní auto**: vysoká hodnota pro uživatele,
   bez nových zdrojů dat.
4. **#18 Moje hledání** → **#17 Hlídací pes** (po #8) → **#20 Rodinný režim**.
5. **#15 Elektro simulátor**, **#22 Rozměry**, **#23 NCAP**: podle toho, jak rychle půjde
   doplnit data.
6. **#26 SEO stránky**, **#24 Poptávka u dealera**, **#25 Skladové vozy**: až u veřejné
   verze (1.x), kdy jde o návštěvnost a obchodní model.

## Otevřené otázky

- Je cílovka i firemní zákazník (#14, #24), nebo zatím jen soukromý kupec?
- Chceme do 1.0 nějaký obchodní model (#24), nebo zůstává portál čistě nekomerční?
- Kdo bude ručně spravovat data, která scraper nezíská (NCAP, dealeři): admin, nebo nová
  role z [../roles/roles.md](../roles/roles.md)?
