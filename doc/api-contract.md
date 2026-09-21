# API Contract – DriveWise AI

Source of truth for the backend's `/api/*` endpoint signatures and shared request/response shapes,
per `doc/prompt/CLAUDE.md`. Backend Pydantic schemas in `backend/app/schemas` must match this
document; when one changes, update this file in the same change.

(The UI, `backend/app/ui/`, consumes these same Pydantic models directly in-process rather than
over HTTP - see `backend/README.md`'s UI section - so it has no separate wire-format types to keep
in sync with this doc the way a browser-based client would. This contract still describes the real,
unchanged `/api/*` behavior for any other client.)

This is drafted (not yet implemented) against the normalized catalog schema proposed for
`brands / models / trims / powertrains / configurations / colors / option_items /
option_availability / prices / source_documents` (see conversation history / future
`doc/data-model.md`). Nothing here is implemented yet — no backend exists in the repo.

## Conventions

- Base path: `/api`
- All responses: `application/json`
- Money is always `{ "amount": number, "currency": "CZK" }` — never a bare number or a formatted
  string. `amount` is the VAT‑included consumer price unless a field name says otherwise
  (`amount_excl_vat`).
- Timestamps: ISO 8601 (`2026-07-20T10:00:00Z`)
- List endpoints are paginated: `?page=1&page_size=20`, response wrapped as
  `{ "items": [...], "page": 1, "page_size": 20, "total": 137 }`
- Errors: `{ "error": { "code": "string", "message": "string", "details": {} } }` with a matching
  HTTP status (400 validation, 404 not found, 422 unprocessable, 500 server error)
- No auth on `/api/*` in v1 (see architecture doc's bonus features) — endpoints are unauthenticated.
  The bundled UI has its own email-code login (admin console, API-key dialog; see
  `backend/README.md`'s Login section), but it calls the service layer in-process and does not
  go through these endpoints, so this contract is unaffected
- Language: all free-text fields meant for display (`explanation`, `flag`, conversation replies)
  are Czech, matching the frontend UI language — prompt the Claude integration accordingly. See
  `doc/prompt/CLAUDE.md`.

## Shared schemas

### Money

| field | type | null? |
|---|---|---|
| amount | number | no |
| currency | string (ISO 4217, e.g. `CZK`) | no |

### VehicleSummary

The recommendation‑card / results‑grid shape — one row per `configuration`, flattened for display.
Implemented as `backend/app/schemas/vehicle.py`'s `VehicleSummary`; the UI (`backend/app/ui/`)
renders it directly, field names as-is (`price` is a real `Money` object, `id` is the numeric
`configuration_id`).

| field | type | null? | notes |
|---|---|---|---|
| configuration_id | integer | no | |
| brand | string | no | |
| model | string | no | |
| trim | string | no | |
| price | Money | no | current price (`prices` row with `valid_to IS NULL`) |
| match_score | integer (0–100) | yes | null outside a recommendation context (e.g. plain catalog browse) |
| specs | string[] | no | short display tags, e.g. `["AWD", "5 seats", "Hybrid"]` — derived, not a DB column |
| flag | string | yes | Czech, matching the UI language (see `doc/prompt/CLAUDE.md`) — e.g. `"Nad rozpočtem o ~2 200 Kč"` — reserved for a future graceful over-budget-inclusion feature; the current recommendation engine treats budget as a hard filter, so this is always null for now |
| top_pick | boolean | no | default `false` |
| thumbnail_url | string | yes | no image data exists in the scraped source yet — expect null for the foreseeable future |
| explanation | string | yes | AI-generated, grounded only in this vehicle's own specs (never invents attributes). Null outside a chat context, or if the AI layer isn't configured |

### VehicleDetail

Extends `VehicleSummary` for a single configuration's detail page.

| field | type | null? | notes |
|---|---|---|---|
| ...VehicleSummary fields | | | |
| powertrain | PowertrainSpec | no | |
| colors | ColorOption[] | no | |
| standard_equipment | string[] | no | names only, `availability = standard` |
| optional_equipment | OptionLine[] | no | `availability = optional`, includes surcharge |
| price_history | PricePoint[] | no | see below |

### PowertrainSpec

| field | type | null? |
|---|---|---|
| fuel_type | enum(petrol, diesel, hybrid, mild_hybrid, phev, electric) | no |
| transmission | string | yes |
| drivetrain | enum(fwd, rwd, awd) | no |
| power_kw | integer | yes |
| power_hp | integer | yes |
| consumption_min | number | yes |
| consumption_max | number | yes |
| consumption_unit | enum(l_100km, kwh_100km) | yes |
| co2_min_g_km | integer | yes |
| co2_max_g_km | integer | yes |

### ColorOption

| field | type | null? |
|---|---|---|
| name | string | no |
| finish_type | enum(solid, metallic, pearlescent) | yes |
| surcharge | Money | no |

### OptionLine

| field | type | null? |
|---|---|---|
| name | string | no |
| category | enum(equipment, package, warranty, service) | no |
| surcharge | Money | no |

### PricePoint

| field | type | null? |
|---|---|---|
| valid_from | date | no |
| valid_to | date | yes |
| price | Money | no |
| lowest_price_30d | Money | yes |

### StructuredRequirements

Output of the AI requirement‑extraction step (architecture.md's Claude‑extraction example),
input to the recommendation engine's filter/rank step.

| field | type | null? | notes |
|---|---|---|---|
| body_type | string | yes | e.g. `"SUV"` |
| min_seats | integer | yes | |
| budget_max | Money | yes | |
| fuel_type | string | yes | |
| drivetrain | enum(fwd, rwd, awd) | yes | |
| priorities | string[] | no | free‑text priority tags, e.g. `["reliability", "cold-weather"]`; default `[]` |
| notes | string | yes | anything extracted that doesn't map to a typed field above |

### UserRequirement

The human‑readable "requirements drawer" card. One `UserRequirement` is produced per populated
field in `StructuredRequirements` (`app/services/conversation.py`'s `_to_user_requirements` maps
structured → display; the UI just renders the result).

| field | type | null? |
|---|---|---|
| label | string | no |
| value | string | no |
| source | string | no |
| changed | boolean | no |

### ChatMessage / ConversationTurn

```
ChatMessage        { role: "user" | "assistant", text: string }
ConversationTurn   { userText, assistantText, stageName, requirements: UserRequirement[], cars: VehicleSummary[] }
```

## Endpoints

### `POST /api/conversations`

Start a new conversation. No body required.

**Response `201`**
```json
{ "conversation_id": "uuid", "intro_message": "string" }
```

### `POST /api/conversations/{conversation_id}/messages`

Send a user message; get back the assistant's reply plus the updated structured requirements and
shortlist. `app/services/conversation.py`'s `orchestrator.handle_message` implements this; the UI
calls that method directly rather than this HTTP endpoint (see `backend/README.md`'s UI section) -
this route exists for any other client.

**Request**
```json
{ "text": "We're a family of 4 and head to the mountains almost every weekend for skiing." }
```

**Response `200`**
```json
{
  "assistant_text": "string",
  "requirements": [ "UserRequirement", "..." ],
  "structured_requirements": "StructuredRequirements",
  "vehicles": [ "VehicleSummary", "..." ],
  "searched": "boolean"
}
```

`searched` is `false` while the AI is still asking follow-up questions (not enough was known to
search on yet - `vehicles` is always `[]` in that case) and `true` once the recommendation engine
actually ran this turn (`vehicles` can still legitimately be `[]` there - a real search that found
nothing). A client falling back to an unfiltered catalog browse before the first real search (see
`backend/app/ui/state.py`'s `ConversationState.has_narrowed`) needs this to tell "haven't searched
yet" apart from "searched, found nothing" - both leave `vehicles` empty.

### `GET /api/vehicles`

Catalog search/browse, independent of the chat flow (results grid without a conversation).

**Query params**: `body_type`, `min_seats`, `budget_max`, `currency`, `fuel_type`, `drivetrain`,
`market` (default `CZ`), `sort` (`price_asc` | `price_desc` | `alpha`, default: `configurations.id`
order), `page`, `page_size`

**Response `200`**: paginated list of `VehicleSummary` (`match_score` and `flag` are null here —
those only apply inside a recommendation context)

### `GET /api/vehicles/{configuration_id}`

**Response `200`**: `VehicleDetail`
**Response `404`**: unknown configuration_id

### `GET /api/vehicles/compare`

**Query params**: `ids` (comma‑separated `configuration_id`s, 2–4)

**Response `200`**
```json
{ "vehicles": [ "VehicleDetail", "..." ] }
```

### `GET /api/models/{model_id}`

Model overview: all trims and their configurations, for a "choose your trim" browsing page.

**Response `200`**
```json
{
  "brand": "string",
  "model": "string",
  "category": "string | null",
  "trims": [
    { "id": "integer", "name": "string", "configurations": [ "VehicleSummary", "..." ] }
  ]
}
```

### `GET /api/brands`

**Response `200`**: `{ "items": [ { "id": "integer", "name": "string", "slug": "string" } ] }`

## Open items for the backend implementation

- `match_score`, `flag`, and `explanation` are recommendation‑engine/AI outputs, not stored
  fields. Implemented: `match_score` (weighted scorer over drivetrain/priority/budget‑headroom
  matches) and `explanation` (per‑vehicle Claude call). Not implemented: `flag` — the engine
  currently treats budget as a hard filter rather than gracefully including near‑budget
  over-shoots with a warning badge.
- `thumbnail_url` has no source yet; either scope image sourcing into the scraper later or drop the
  field from `VehicleSummary` until there's a plan for it.
- `GET /api/vehicles` filtering by `budget_max` needs a currency‑aware comparison against
  `prices.currency` — implemented: rejects nothing yet, just filters on `currency = <param>`
  server-side rather than converting; a cross‑currency budget silently returns zero matches
  rather than erroring, which is arguably wrong — worth revisiting.
- Conversation state (message history + accumulated `StructuredRequirements`) is held **in a
  process‑local in‑memory dict**, keyed by `conversation_id` — not persisted, lost on restart,
  and won't work past a single backend worker process. The DB schema doesn't have
  conversation/message tables; adding them is a separate design decision, not made yet.
- `min_seats` (in `StructuredRequirements` and `GET /api/vehicles` query params) has no backing
  data — neither sample source document states seat count anywhere. Accepted by the schema,
  not actually filterable yet.
- The AI layer (`app/ai/requirement_interpreter.py`, `app/ai/explanation_generator.py`) was
  written without access to a live `ANTHROPIC_API_KEY` and has not been exercised against the
  real Claude API — verify prompt behavior (JSON-only compliance, follow-up-question quality)
  before relying on it.
