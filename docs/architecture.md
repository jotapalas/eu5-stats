# Architecture

## Overview

```
                    ┌──────────────────────── backend (FastAPI, port 8000) ────────────────────────┐
 browser ── /api ──▶│ app/stats/api.py ──▶ Store (SQLite: data/eu5stats.db)                        │
 (Vite / nginx)     │        │                     ▲                                                │
                    │        ▼                     │ store_stats                                    │
 POST sessions ────▶│ Ingestor.add_upload ──▶ data/uploads/<sha256>.eu5 ──▶ worker thread          │
                    │                                                        └─ extract() ─ app/eu5 │
                    └───────────────────────────────────────────────────────────────────────────────┘
 tools/export_static.py ── Store ──▶ frontend/dist-public/data/*.json ──▶ Cloudflare Pages (read-only)
```

Two backend layers:

- **`app/eu5/`**: a self-contained decoder for the binary format. It does not depend on `app/stats`. See
  [save-format.md](save-format.md).
- **`app/stats/`**: campaigns, sessions and saves. Uploads are processed in the background, results
  go to SQLite, and query endpoints read them.

The frontend (`frontend/`) is a React SPA. It talks to the backend through `/api`, so no CORS is needed.
A read-only build reads static JSON files instead (see [Read-only mode](#read-only-public-build)).

## Domain model

```
campaign ─< session ─< save ─< country_snapshot (one per tracked country)
    │                    ├─< country_metrics   (save, country_id, metric) -> value
    │                    └─< country_history   (save, country_id, metric, year) -> value
    └─< campaign_countries  (tracked list: tag as added, country_id, active, main player)
```

- A **campaign** is one multiplayer playthrough. A **session** is one evening of play, usually with one
  save per in-game year. A **save** is one uploaded file.
- Stats are keyed by **`country_id`**, the game's internal id. It does not change when a country changes
  tag (ENG forming GBR), so a country keeps a single series. Results are labelled with the country's
  *current* tag (from its latest effective snapshot). Queries also accept past tags or the tag it was
  added with.
- Each snapshot stores the players controlling the country in that save (empty list = AI). The optional
  `campaign_countries.player` overrides the name shown in campaign-wide views.

### Effective saves

Players often upload overlapping saves (an autosave and a manual save of the same date, or a re-upload).
Every campaign-wide query uses `EFFECTIVE_SAVES` in [`db.py`](../backend/app/stats/db.py): saves with
`status = 'done'` where, for each in-game date (`game_hours`), only the latest upload (highest `id`)
counts. Session summaries use the session's own saves.

### Tracked countries

The worker extracts every country played by a human plus every *active* entry in
`campaign_countries` (`Store.tracked_countries`). After storing a save, `_update_tracked`:

1. resolves pending tags (`country_id IS NULL`) to ids,
2. adds played countries that have no entry (so humans are tracked automatically),
3. stores rows only for active countries.

Removing a country sets `active = 0`. Its data is kept and it is not re-added automatically.
Reprocessing applies the *current* list, so a removed country loses its rows in reprocessed saves.

## Processing pipeline

1. `POST /campaigns/{id}/sessions` (multipart) → `Store.create_session`, then `Ingestor.add_upload`
   per file: stream to `uploads/<tmp>.part` while hashing, validate the 32-byte header, register the
   save (`pending`, `error` or `duplicate`, deduplicated per campaign by SHA-256), rename to
   `<sha256>.eu5`, wake the worker. The request returns 202 straight away.
2. The single worker thread (`Ingestor._run`) wakes on an event or every 5 s and claims one
   `pending` save (`processing`).
3. `extract.extract(bytes, tokens, tracked)` parses the metadata and only the gamestate sections it
   needs (see [save-format.md](save-format.md#partial-parsing)). It returns a `SaveStats`: one
   `CountryStats(country_id, tag, players, metrics)` per country plus yearly history rows from the
   game's `historical_*` lists.
4. `Store.store_stats` replaces all rows for that save (so it is idempotent), sets `done`, and adds a
   `warning` if the save's `playthrough_id` differs from the campaign's other saves. On any exception the
   save is marked `error` with the message.

On startup, saves left in `processing` are reset to `pending`. Uploaded files are the source of
truth. `reprocess` re-queues saves and the database can be rebuilt from `data/uploads/`.

Metrics are plain functions over the country record (`METRICS` in
[`metrics.py`](../backend/app/stats/metrics.py)). The `/metrics` endpoint, validation and
[metrics.md](metrics.md) are all derived from that list.

## SQLite

`Store` uses raw `sqlite3`, with a new connection per call (WAL, `foreign_keys=ON`). The schema is the
`SCHEMA` string in `db.py` (`CREATE TABLE IF NOT EXISTS`, no migrations):

| Table | Key | Notes |
|---|---|---|
| `campaigns` | `id` | unique `name` |
| `sessions` | `id` | `played_on` (real date), `notes` |
| `saves` | `id`, unique `(campaign_id, sha256)` | `status`, `error`, `warning`, `game_hours`, `game_date`, playthrough, version |
| `campaign_countries` | `id`, unique `(campaign_id, country_id)` | `tag` as added, `active`, `player` |
| `country_snapshots` | `(save_id, country_id)` | tag in that save, `players` JSON |
| `country_metrics` | `(save_id, country_id, metric)` | `value REAL` |
| `country_history` | `(save_id, country_id, metric, year)` | the latest save wins per year in queries |

Deleting a session cascades to its saves and their rows. Upload files no longer referenced by any
campaign are deleted.

## Frontend

React 18 + Vite + TypeScript, TanStack Query/Table, Recharts, Tailwind. UI text is Spanish
(`src/i18n.ts`) and code is English.

| Path | Contents |
|---|---|
| `src/api/` | `client.ts` (fetch, static paths), `types.ts` (mirrors `Store` dicts), `hooks.ts` (queries) |
| `src/lib/` | `format.ts` (game dates, numbers, rank / lower-is-better sets), `colors.ts`, `mode.ts` |
| `src/components/` | `TimeSeriesChart`, pickers, UI primitives |
| `src/pages/` | one component per route; `CampaignLayout` provides `useCampaignCtx()` |

- Campaign-scoped query keys start with `["campaign", id]`. `CampaignLayout` invalidates them when
  `saves_done` changes. While saves are pending, campaign and session queries poll every 2 s.
- The X axis is the game date as a fractional year (365-day years), with one point per save.
- Country colours come from 8 fixed categorical hues assigned by sorted tag. Countries 9–16 reuse them
  with a dashed line, and the rest are grey.

### Read-only public build

With `VITE_READONLY=1` (`src/lib/mode.ts`), `get()` maps each API path to a static file
(`staticPath` in `client.ts`), writes are rejected and management UI is hidden.
[`tools/export_static.py`](../backend/tools/export_static.py) writes those files with the same `Store`
methods the API uses. Its docstring lists the path mapping. A new read endpoint used by the UI must be
added to both.
