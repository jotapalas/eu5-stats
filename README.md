# eu5-stats

A FastAPI service that decodes **Europa Universalis V** binary save files (`.eu5`) and tracks per-player statistics across multiplayer campaigns.

It does two things:

1. **Decode**: turn a `.eu5` save into JSON (`POST /decode`).
2. **Track stats**: group saves into *campaigns* and *sessions*, extract per-player metrics (gold, population, armies, score, and more) in a background worker, store them in SQLite, and serve time series, player timelines and session summaries.

## Requirements

- Docker with Docker Compose (recommended), **or**
- Python ≥ 3.12

## Quick start (Docker)

```bash
make build      # build the image (includes test dependencies)
make up         # start the API on http://localhost:8000
make logs       # follow logs
make down       # stop
```

Interactive API docs: <http://localhost:8000/docs>.

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
curl  localhost:8000/campaigns/1/players/<player-name>
curl  localhost:8000/sessions/1/summary
```

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
| GET | `/campaigns/{id}` | Campaign details + latest snapshot per player |
| PATCH | `/campaigns/{id}` | Rename / change description |
| DELETE | `/campaigns/{id}` | Delete (only if it has no sessions) |
| POST | `/campaigns/{id}/reprocess` | Re-extract every save of the campaign |
| POST | `/campaigns/{id}/sessions` | Create a session and upload saves (multipart: `files`, `name`, `played_on`, `notes`) |
| GET | `/campaigns/{id}/sessions` | List sessions |
| GET | `/sessions/{id}` | Session details and its saves |
| POST | `/sessions/{id}/saves` | Add more saves to a session |
| DELETE | `/sessions/{id}` | Delete a session, its saves and orphaned files |
| GET | `/sessions/{id}/summary` | Start / end / delta of every metric per player |
| GET | `/saves/{id}` | Save details and processing status |
| POST | `/saves/{id}/reprocess` | Re-extract one save |
| GET | `/campaigns/{id}/series?metric=&player=&session=` | Metric over time per player |
| GET | `/campaigns/{id}/players/{name}` | All metrics of a player over time |
| GET | `/campaigns/{id}/history?metric=` | Yearly series kept by the game (`population`, `tax_base`, `economical_base`) per country tag |

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

## Project layout

```
app/
  main.py            FastAPI app factory, /health, /decode
  eu5/               binary save decoder (container, lexer, parser, values, tokens)
  stats/             campaigns/sessions: API, SQLite store, ingest worker, extraction, metrics
tools/token_stats.py report on unresolved native tokens
tokens/eu5.txt       native token id -> name table
tests/               pytest suite (+ fixtures/test_save.eu5, not versioned)
data/                runtime data: eu5stats.db and uploads/ (not versioned)
```

## Useful commands

```bash
make shell      # bash inside the container
make db-shell   # sqlite3 on data/eu5stats.db
```
