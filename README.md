# eu5-stats

A FastAPI service that decodes **Europa Universalis V** binary save files (`.eu5`) and tracks per-country statistics across multiplayer campaigns.

It does two things:

1. **Decode**: turn a `.eu5` save into JSON (`POST /decode`).
2. **Track stats**: group saves into *campaigns* and *sessions*, extract per-country metrics (gold, population, armies, score, and more) in a background worker, store them in SQLite, and serve time series, country timelines and session summaries.

## Requirements

- Docker with Docker Compose (recommended), **or**
- Python ≥ 3.12

## Quick start (Docker)

```bash
make build         # build the images (the API image includes test dependencies)
make up            # start the API on http://localhost:8000 and the web UI on http://localhost:5173
make logs          # follow logs of all services (backend-logs / web-logs for one)
make down          # stop
```

Web UI: <http://localhost:5173>. Interactive API docs: <http://localhost:8000/docs>.

Compose mounts the repository at `/app`, so code changes and saves in the repo root are visible without rebuilding. Run `make help` to list every target.

## Typical workflow

```bash
# 1. Create a campaign
make campaign NAME="Sweden MP" DESC="Sunday group"
# -> {"id": 1, ...}

# 2. Upload a session's saves (every *.eu5 in a folder, e.g. one save per in-game year)
make session CAMPAIGN=1 DIR=~/saves/session1 NAME="Session 1" PLAYED_ON=2026-11-16

# 3. Check progress (saves are processed in the background)
curl localhost:8000/campaigns/1

# 4. Query statistics
curl "localhost:8000/campaigns/1/series?metric=population"
curl "localhost:8000/campaigns/1/history?metric=tax_base"
curl  localhost:8000/campaigns/1/countries/ENG
curl  localhost:8000/sessions/1/summary
```

### Tracked countries

Statistics are stored per **country** (tag), not per player: several players may play the same tag over a
campaign, and each snapshot records which players controlled it (empty for AI). Each campaign has a list of
tracked countries:

- Countries played by humans are added automatically when a save is processed.
- Add any other country (e.g. an AI rival) with `POST /campaigns/{id}/countries` `{"tag": "DAN"}`.
- Remove one with `DELETE /campaigns/{id}/countries/{tag}`: data already extracted is kept, saves processed
  afterwards ignore it, and it is not re-added automatically.
- Changes apply to saves processed afterwards; `reprocess` applies the current list to existing saves (a removed
  country then loses its rows in the reprocessed saves).
- A country is followed by its internal id, so a tag change (ENG forming GBR) keeps a single series. Results are
  labelled with the current tag, and past tags also work in queries.

Uploads are content-addressed (SHA-256): uploading the same file twice to a campaign is reported as `duplicate`. When several saves share the same in-game date, the most recently uploaded one is used for campaign-wide queries.

If metric extraction changes, recompute everything from the stored saves with:

```bash
make reprocess CAMPAIGN=1
```

## API

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Status and number of known native tokens |
| POST | `/decode` | Decode a save to JSON (see below) |
| GET | `/metrics` | Available metrics and history metrics |
| POST | `/campaigns` | Create a campaign `{name, description}` |
| GET | `/campaigns` | List campaigns |
| GET | `/campaigns/{id}` | Campaign details + latest snapshot per country |
| PATCH | `/campaigns/{id}` | Rename / change description |
| DELETE | `/campaigns/{id}` | Delete (only if it has no sessions) |
| GET | `/campaigns/{id}/countries` | Tracked countries (active and removed) with past tags and players |
| POST | `/campaigns/{id}/countries` | Track a country `{tag}` (409 if already tracked) |
| DELETE | `/campaigns/{id}/countries/{tag}` | Stop tracking a country (data is kept) |
| GET | `/campaigns/{id}/countries/{tag}` | All metrics, tag and players of a country over time |
| POST | `/campaigns/{id}/reprocess` | Re-extract every save of the campaign |
| POST | `/campaigns/{id}/sessions` | Create a session and upload saves (multipart: `files`, `name`, `played_on`, `notes`) |
| GET | `/campaigns/{id}/sessions` | List sessions |
| GET | `/sessions/{id}` | Session details and its saves |
| POST | `/sessions/{id}/saves` | Add more saves to a session |
| DELETE | `/sessions/{id}` | Delete a session, its saves and orphaned files |
| GET | `/sessions/{id}/summary` | Start / end / delta of every metric per country |
| GET | `/saves/{id}` | Save details and processing status |
| POST | `/saves/{id}/reprocess` | Re-extract one save |
| GET | `/campaigns/{id}/series?metric=&tag=&session=` | Metric over time per country |
| GET | `/campaigns/{id}/history?metric=` | Yearly series kept by the game (`population`, `tax_base`, `economical_base`) per country, with the players who played it |

Save status is one of `pending`, `processing`, `done`, `error` (with an `error` message), plus an optional `warning` if a save belongs to a different playthrough than the rest of the campaign.

### `POST /decode`

```bash
make decode SAVE=autosave.eu5                            # writes autosave.eu5.json
make decode SAVE=autosave.eu5 PARAMS='sections=metadata'
```

Query parameters:

- `sections` – comma-separated subset of `header,metadata,gamestate` (default: all)
- `select` – comma-separated top-level gamestate keys to keep, e.g. `countries,played_country` (much faster than a full decode)
- `dates` – render date-like integers as `Y.M.D` strings (default `true`)
- `strict` – fail on unknown value tokens instead of returning a partial result with `errors` (default `true`)

The response also contains `unknown_tokens`: native token ids without a name and how often they appeared.

## Native token names

Field names stored as native tokens (not strings) are rendered as `"0xNNNN"` unless they are listed in [tokens/eu5.txt](tokens/eu5.txt) (`<id> <name>` per line, hex or decimal). To find candidates:

```bash
make token-stats            # unresolved tokens across saves in ., saves/ and tests/fixtures
make token-stats ARGS=--json
```

## Running without Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
pytest
```

Data (SQLite database and uploaded saves) goes to `./data` by default; override with the `EU5_DATA_DIR` environment variable.

## Tests

```bash
make test                    # whole suite in the container
make test ARGS="-k units"    # pass extra pytest arguments
```

Most tests need a real save at `tests/fixtures/test_save.eu5`. Save files are git-ignored (`*.eu5`), so on a fresh clone you must provide that fixture yourself; without it those tests are skipped and only the synthetic unit tests run. Any `*.eu5` in the repo root is also picked up by the per-save tests.

## Frontend

`frontend/` is a React + Vite + TypeScript SPA (UI in Spanish) for viewing and managing campaigns:

- **Ranking**: latest snapshot of every country, sortable by any metric.
- **Comparativa**: one metric over time for selected countries in a single metric list: metrics the game keeps as yearly history (population, tax base, economic base) use that series; the rest use one point per save.
- **Ficha de país**: small multiples of every metric for one country, with players and tag changes.
- **Sesiones**: upload saves (with progress and live processing status), per-session changes, reprocessing.
- **Ajustes**: tracked countries, reprocess, rename/delete the campaign.

The browser talks to the API through `/api` (Vite proxy in development, nginx in production), so no CORS is needed.

```bash
make web-logs      # dev server logs
make web-lint      # tsc + eslint
make web-test      # vitest
make web-build     # production image (nginx serving the build and proxying /api)
make web-prod-up   # serve it on http://localhost:8080
```

Without Docker: `cd frontend && npm install && API_URL=http://localhost:8000 npm run dev`.

## Project layout

```
backend/
  app/main.py          FastAPI app factory, /health, /decode
  app/eu5/             binary save decoder (container, lexer, parser, values, tokens)
  app/stats/           campaigns/sessions: API, SQLite store, ingest worker, extraction, metrics
  tools/token_stats.py report on unresolved native tokens
  tokens/eu5.txt       native token id -> name table
  tests/               pytest suite (+ fixtures/test_save.eu5, not versioned)
  data/                runtime data: eu5stats.db and uploads/ (not versioned)
frontend/
  src/api/             fetch client, response types, TanStack Query hooks
  src/lib/             formatting (game dates, numbers) and country colours
  src/components/      chart, pickers, UI primitives
  src/pages/           one component per route
```

## Useful commands

```bash
make shell      # bash inside the API container
make web-shell  # sh inside the frontend container
make db-shell   # sqlite3 on data/eu5stats.db
```
