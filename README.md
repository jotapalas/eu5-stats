# eu5-stats

Statistics for **Europa Universalis V** multiplayer campaigns. Upload the saves after each session.
The service decodes the binary `.eu5` files, extracts per-country metrics (economy, size, military,
state), stores them in SQLite, and shows rankings, comparisons and per-country histories in a web UI. A
read-only copy can be published as a static site.

- **Backend**: FastAPI + a self-contained decoder for the binary save format (`backend/`).
- **Frontend**: React + Vite SPA, UI in Spanish (`frontend/`).

## Quick start

Requires Docker with Compose.

```bash
make build && make up     # API on http://localhost:8000 (docs at /docs), web UI on http://localhost:5173
make campaign NAME="Sweden MP"
make session CAMPAIGN=1 DIR=~/saves/session1 NAME="Session 1" PLAYED_ON=2026-11-16
```

Open <http://localhost:5173>. Saves are processed in the background, a few seconds each. Run
`make help` to list every target.

## Documentation

| I want to… | Read |
|---|---|
| Understand the web UI and the charts | [docs/user-guide.md](docs/user-guide.md) |
| Know what each metric means | [docs/metrics.md](docs/metrics.md) |
| Run it, load saves, back up, publish the public site | [docs/operations.md](docs/operations.md) |
| Use the HTTP API | [docs/api.md](docs/api.md) |
| Understand how it works | [docs/architecture.md](docs/architecture.md) |
| Understand the `.eu5` binary format | [docs/save-format.md](docs/save-format.md) |
| Change the code (tests, recipes, conventions) | [docs/development.md](docs/development.md) |

## Project layout

```
backend/
  app/main.py          FastAPI app factory, /health, /decode
  app/eu5/             binary save decoder (container, lexer, parser, values, tokens)
  app/stats/           campaigns/sessions: API, SQLite store, ingest worker, extraction, metrics
  tools/               export_static (public site), token_stats (unknown tokens), metrics_doc (docs)
  tokens/eu5.txt       native token id -> name table
  tests/               pytest suite (fixtures/test_save.eu5 is not versioned)
  data/                runtime data: eu5stats.db and uploads/ (not versioned)
frontend/
  src/api/             fetch client, response types, TanStack Query hooks
  src/lib/             formatting (game dates, numbers), country colours, read-only mode
  src/components/      chart, pickers, UI primitives
  src/pages/           one component per route
docs/                  documentation (metrics.md is generated: make docs)
```
