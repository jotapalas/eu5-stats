# CLAUDE.md

Context for working on this repository. See [README.md](README.md) for user-facing usage.

## What this is

FastAPI service (Python ≥ 3.12) that decodes Europa Universalis V binary saves (`.eu5`) and stores per-country statistics for multiplayer campaigns in SQLite. Two layers:

- `app/eu5/` – a self-contained decoder for the binary Clausewitz/Jomini format. No dependency on `app/stats`.
- `app/stats/` – campaigns/sessions/saves domain: upload → background extraction → SQLite → query endpoints.

Dependencies are minimal on purpose: `fastapi`, `uvicorn`, `python-multipart`, `orjson` (+ `pytest`, `httpx` for tests). No ORM, no pydantic models beyond request bodies, no linter configured.

## Commands

The app normally runs in Docker; the repo is bind-mounted at `/app`.

```bash
make build / make up / make down
make logs                      # all services; backend-logs / web-logs for one
make test                      # pytest in the container
make web-lint / make web-test  # frontend: tsc + eslint / vitest (in the node container)
make test ARGS="tests/test_units.py -x"
make shell                     # bash in the container
make db-shell                  # sqlite3 data/eu5stats.db
make token-stats [ARGS=--json] # unresolved native tokens across saves
```

Locally (no Docker): `pip install -r requirements-dev.txt`, `pytest`, `uvicorn app.main:app --reload`. `pyproject.toml` sets `pythonpath = ["."]` and `testpaths = ["tests"]`.

The repo lives on WSL (`\\wsl.localhost\Ubuntu\root\eu5-stats`); from Windows, git needs `-c safe.directory='*'` (dubious ownership).

## Frontend (`frontend/`)

React 18 + Vite + TypeScript (strict), TanStack Query, TanStack Table, Recharts, Tailwind. UI text in Spanish (all labels in `src/i18n.ts`, including Spanish metric names in `METRIC_LABELS`); code in English.

- Served by the `web` compose service (Vite dev server, port 5173, `node_modules` in an anonymous volume). `/api/*` is proxied to the backend with the prefix stripped (`vite.config.ts`, `API_URL`; `nginx.conf` in the production image, profile `prod`, port 8080). The backend has no CORS on purpose.
- `src/api/types.ts` mirrors the dicts returned by `Store`; update it when a response shape changes. `src/api/hooks.ts`: every campaign-scoped query key starts with `["campaign", id]`; `CampaignLayout` invalidates them all when `saves_done` changes. Campaign/session queries poll every 2 s while saves are pending.
- `CampaignLayout` provides `useCampaignCtx()` (campaign, sorted `tags`, `color(tag)`, `players(tag)`) to the pages.
- Colours (`src/lib/colors.ts`): 8 validated categorical hues (light/dark steps) assigned by sorted tag; countries 9–16 reuse them dashed, the rest grey. Never cycle or generate new hues.
- X axis = game date as a fractional year (`gameDateToYear`, 365-day years), one point per save. `Compare` has no source toggle: a metric listed in `/metrics` `history_metrics` is charted from `/history` (yearly, covers years before the first save), any other from `/series`.
- Rank metrics (`RANK_METRICS` in `src/lib/format.ts`: `score_place`, `great_power_rank`; 1 = best, values up to ~2000) use `TimeSeriesChart rank`: reversed log Y axis with power-of-ten ticks, values <= 0 dropped, legend sorted ascending. `LOWER_IS_BETTER` is broader (also inflation, war exhaustion) and only affects delta colours and sort direction.
- Add a view: page in `src/pages/`, route in `App.tsx`, tab in `CampaignLayout` `TABS` if needed, data hook in `hooks.ts`. New metrics need a Spanish label in `METRIC_LABELS` (otherwise the API description is shown).

## Architecture and data flow

```
POST /campaigns/{id}/sessions (multipart files)
  -> api.create_session -> Store.create_session
  -> Ingestor.add_upload: stream to data/uploads/<tmp>.part, sha256, check header,
     Store.add_save (status pending | error | duplicate), rename to <sha256>.eu5, wake worker
worker thread (Ingestor._run, wakes on Event or every 5 s)
  -> Store.claim_next_pending (status=processing)
  -> extract.extract(bytes, tokens, Store.tracked_countries(campaign)) -> SaveStats
  -> Store.store_stats (replaces all rows for that save; status=done) | Store.mark_error
query endpoints -> Store.series / country_timeline / latest_snapshots / session_summary / history
```

### `app/eu5/` (decoder)

- `container.py` – file = 32-byte ASCII header (`SAV` + hex fields: version, save_type, unknown, metadata_len, trailer, `\n`) + binary metadata block (`metadata_len` bytes) + ZIP with entries `gamestate` and `string_lookup`. `open_save(data, with_gamestate=)`. Errors: `SaveFormatError(ValueError)`.
- `string_lookup.py` – `string_lookup` entry: u8 version, u16 count, u16 unknown, then u16-length-prefixed UTF-8 strings (cp1252 fallback). Validates count/end offset.
- `lexer.py` – every token is a little-endian u16. Control: `EQUAL 0x01`, `OPEN 0x03`, `CLOSE 0x04`. Standard value types (`I32`, `U32`, `F32`, `BOOL`, `QUOTED`, `UNQUOTED`, `F64` = i64/100000, `U64`, `I64`). EU5-specific types, found empirically: `LOOKUP_U8`/`LOOKUP_U16` (index into string_lookup) and `FIXED5_*` (0–7 byte unsigned magnitude, sign in the token, value/100000). Any other u16 is a **native name token** (text lives in the game exe). Unknown tokens inside `EU5_TYPE_RANGE` (0x0d3e–0x0d5f) raise `TokenError` – never guess payload sizes. `iter_tokens()` is a slow, simple reference lexer used by tools/tests only.
- `parser.py` – the hot path.
  - `parse(buf, strings, tokens, *, dates, strict, unknown, errors, select)` builds dicts/lists with a frame stack. Block rules (also in the module docstring): only `k=v` → dict (repeated key → list); only bare values → list; empty → `[]` (`{}` when filtered); mixed → list with `{k: v}` items; `key = tag { ... }` → `{tag: block}`; `{...} = value` → key is the block's compact JSON.
  - `select` is a nested dict `{key: True | {subkey: ...}}`; unselected subtrees are skipped with `skip_value`/`skip_block` using the precomputed `_SIZE` table (payload size per token: >0 fixed, -1 length-prefixed, -2 unknown EU5 type).
  - `index_top_level()` returns `{key: [(start, end), ...]}` byte ranges; parse a single section with `parse(memoryview(buf)[s:e], ...)` → `{key: value}`.
  - `strict=False` closes open frames and appends messages to `errors` instead of raising.
  - The code is micro-optimised (local aliases, branch order in `scalar()` by frequency, inline `buf[i] | buf[i+1] << 8`). Keep that style when touching `parse`, `skip_*` or `index_top_level`.
- `values.py` – dates are i32 **hours since -5000.1.1**, 365-day years, no leap years. `looks_like_date(key, value)`: i32 in years 0..2000 and key not in `NOT_DATE_KEYS`. Only `I32` values are date-converted. `FIXED5_SCALE = 100_000`.
- `tokens.py` – `TokenTable` from `tokens/eu5.txt` (`<id> <name>`, `#` comments). Currently has **no entries**; unresolved ids render as `"0xNNNN"` and are counted in `unknown`.
- `decoder.py` – `decode_save()` used by `POST /decode`; returns `header`, `metadata`, `gamestate`, `unknown_tokens`, optional `errors`.

### `app/stats/`

- `extract.py` – `extract(data, tokens) -> SaveStats`. Parses metadata with `dates=False` to keep raw sortable hours. Metadata fields are native tokens hardcoded as `META_ROOT 0x09de`, `META_DATE 0x06b5`, `META_PLAYTHROUGH_ID 0x096e`, `META_PLAYTHROUGH_NAME 0x096f`, `META_VERSION 0x00ee`, looked up via `tokens.resolve(...)` so they work whether or not the token is named. Gamestate: indexes top level, then parses only `played_country` (players: `name`, `country`), `countries` in two passes (`tags` first to resolve tracked tags → ids, then only the needed `database` entries), `unit_manager`, `subunit_manager`, `war_manager`. Extracts one `CountryStats(country_id, tag, players, metrics)` per played country plus per tracked `(tag, country_id | None)` (by id when known, so tag changes are followed; by tag otherwise; missing countries are skipped). Country ids are string keys in parsed dicts (`database[str(cid)]`). Also emits yearly history `(country_id, tag, metric, year, value)` from `historical_*` lists ending at `last_stat_year`. Raises `ExtractError` (no `played_country`, bad metadata).
- `metrics.py` – `METRICS: list[Metric(name, category, description, fn(country, ctx) -> float)]`; `Context` carries units/subunits/wars. Helpers: `get(d, "a.b.c")`, `num`, `count`, `as_list` (Paradox writes 1-element lists as a bare value), `_field(path)`, `_len(path)`. Paradox omits zero/false fields, so every lookup defaults to 0. `HISTORY_FIELDS` maps `historical_*` fields to history metric names. `/metrics` and validation in `api.py` are derived from these, nothing else to register.
- `db.py` – `Store` with raw `sqlite3`; a new connection per call via `connect()` (WAL, `foreign_keys=ON`, commit/rollback via `with db`). Public methods open a connection and call private `_campaign(db, id)` / `_session(db, id)` helpers, which also serve as existence checks (raise `NotFound`). Schema is `CREATE TABLE IF NOT EXISTS` in `SCHEMA`; there are no migrations. `EFFECTIVE_SAVES` SQL: campaign saves with `status='done'` where, per `game_hours`, the highest `id` (latest upload) wins – used by every campaign-wide query. `store_stats` is idempotent (deletes then reinserts snapshot/metrics/history rows) and sets a `warning` when the save's `playthrough_id` differs from the campaign's other saves.
  - Stats are per country: `country_snapshots(save_id, country_id, tag, players JSON)`, `country_metrics`, `country_history`, all keyed by `country_id` (stable across tag changes). Results are labelled by the country's *current* tag (latest effective snapshot, `_label`); `_country_id` resolves current, added-as or past tags.
  - `campaign_countries` is the editable tracked list (`tag` as added, `country_id` NULL until resolved, `active`). `store_stats` → `_update_tracked` resolves pending tags, auto-adds played countries without an entry, and stores rows only for active countries. Removing (`active=0`) keeps data and prevents auto re-adding.
- `ingest.py` – `Ingestor`: content-addressed files `uploads/<sha256>.eu5` shared across campaigns (dedupe is per campaign via `UNIQUE(campaign_id, sha256)`); only the header is validated at upload time. Single daemon worker thread; `start()` resets `processing` → `pending`. `process_pending()` runs synchronously (tests use it instead of the thread).
- `api.py` – `APIRouter`; gets `Store`/`Ingestor` from `request.app.state`. Endpoints are sync `def` (FastAPI runs them in a threadpool). Returns plain dicts.

### `app/main.py`

`create_app(data_dir=EU5_DATA_DIR or ./data, *, start_worker=True)` wires `TokenTable`, `Store(data_dir/eu5stats.db)`, `Ingestor(data_dir/uploads)`, the stats router, exception handlers (`NotFound` → 404, `Conflict` → 409) and the `/health` and `/decode` endpoints. Module-level `app = create_app()` is what uvicorn serves. Decoder errors in `/decode` map to 422.

## Conventions

- Code, comments, docstrings and identifiers in English.
- Every module starts with a docstring and `from __future__ import annotations`; format discoveries are documented in module docstrings (keep them in sync when the format understanding changes).
- Modern typing (`dict[str, int]`, `X | None`), `@dataclass` for data records, module-level constants in UPPER_CASE.
- Domain errors are exceptions defined in the layer (`SaveFormatError`, `TokenError`, `ExtractError`, `NotFound`, `Conflict`) and mapped to HTTP in `main.py` / `api.py`, not raised as `HTTPException` from `db.py`.
- Raw SQL with named (`:campaign`) or `?` parameters; f-strings only for composing trusted SQL fragments like `EFFECTIVE_SAVES`.
- JSON responses from `/decode` use `orjson` directly (large payloads).
- Comments are terse and explain *why*; lines up to ~110 chars.

## Recipes

- **Add a per-country metric**: append a `Metric(...)` to `METRICS` in `app/stats/metrics.py` (must return `float`). If it needs data outside the country record, add the section to `extract.py` (parse it via `_section` with a `select` as narrow as possible) and a field to `Context`. Existing campaigns need `POST /campaigns/{id}/reprocess`. Tests: `test_all_metrics_numeric` checks every metric is a float for every country; update `test_stats_api.py` only if `/metrics` expectations change.
- **Add a history metric**: add `historical_<x>` → `<name>` to `HISTORY_FIELDS`; update the assertions in `tests/test_extract.py::test_history` and `tests/test_stats_api.py::test_campaign_endpoints` (they list the exact set).
- **New/unknown value token** (decode fails with `Unknown EU5 value token 0x0dXX`): add the constant to `lexer.py` (`KNOWN`, and `iter_tokens`), its payload size to `_build_size_table`, its decoding to `parser.scalar()`, its type name to `tools/token_stats.TYPE_NAMES`, and a synthetic test in `tests/test_units.py`.
- **Name native tokens**: add `<id> <name>` lines to `tokens/eu5.txt`. Tests deliberately use an empty `TokenTable()` so keys stay `"0xNNNN"`; do not make tests depend on the file's contents.
- **Add an endpoint**: add it to `app/stats/api.py` (or `main.py` for decoder-level endpoints), put the SQL in a `Store` method, raise `NotFound`/`Conflict` for 404/409, and extend `tests/test_stats_api.py` (real save) or `tests/test_stats_db.py` (synthetic `SaveStats`).
- **Change the DB schema**: edit `SCHEMA`. Because it uses `CREATE TABLE IF NOT EXISTS`, existing databases are not altered – either add explicit `ALTER TABLE` logic in `Store.__init__` or tell the user to delete `data/eu5stats.db` and re-upload/reprocess. Raw save files in `data/uploads/` are the source of truth; everything in the DB can be recomputed.

## Tests

- `tests/test_units.py` – synthetic token streams (helpers `tok`, `key`, `i32`, `run`); fast, no files needed. Preferred place for decoder logic tests.
- `tests/test_stats_db.py` – `Store` queries with synthetic `SaveStats` (helper `stats(year, {name: (tag, metrics)})`).
- `tests/test_saves.py` – parametrised over every `*.eu5` in the repo root and `tests/fixtures` (`save_path` fixture), plus checks on `test_save.eu5`.
- `tests/test_extract.py`, `tests/test_stats_api.py` – use `tests/fixtures/test_save.eu5` (14-player MP save at 1367.1.5, version 1.4.7; e.g. player "Miranda" = ENG, 157 locations). They assert exact values from that save.
- `*.eu5` is git-ignored, so the fixture is **not versioned**: on a machine without it, `mp_save_bytes` tests skip and `save_path` tests have no parameters. Real saves are 25–40 MB; full-decode tests are slow.
- API tests use `create_app(tmp_path, start_worker=False)` and drive processing with `app.state.ingestor.process_pending()`.
- `test_full_decode` asserts every unresolved token count is even (metadata is repeated at the start of the gamestate) and `test_container` asserts header `(version, save_type) == (3, 3)`.

## Gotchas

- `data/` (DB + uploads) is git-ignored and bind-mounted; it may contain real user data – don't delete it without asking.
- `tests/test_saves.py`'s docstring mentions `./saves`, but `conftest.py` only scans the repo root and `tests/fixtures`; `make token-stats` scans `.`, `saves/` and `tests/fixtures`.
- `app/main.py` builds `app = create_app()` at import time, so importing it (e.g. `tests/test_stats_api.py`) opens `data/eu5stats.db` unless `EU5_DATA_DIR` points elsewhere.
- Reprocessing uses the *current* tracked list: a removed country loses its rows in reprocessed saves.
- Deleting a campaign is refused (409) while it has sessions.
- The worker is a single thread and extraction is CPU-bound; uploads return 202 immediately and the client must poll save/campaign status.
- No auth, CORS or upload size limit.
