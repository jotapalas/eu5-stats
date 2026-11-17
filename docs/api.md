# API reference

The backend listens on `http://localhost:8000`. Interactive docs (OpenAPI) are at
<http://localhost:8000/docs>. The browser reaches the same API under `/api` (the prefix is stripped by the
Vite proxy or nginx).

All responses are JSON. Errors use `{"detail": "..."}` with 404 (not found), 409 (conflict) or 422
(validation, unknown metric, undecodable save). There is no authentication.

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Status and number of known native tokens |
| POST | `/decode` | Decode a save to JSON ([below](#post-decode)) |
| GET | `/metrics` | Available metrics and history metrics |
| POST | `/campaigns` | Create a campaign `{name, description}` |
| GET | `/campaigns` | List campaigns |
| GET | `/campaigns/{id}` | Campaign details + latest snapshot per country (`latest`) |
| PATCH | `/campaigns/{id}` | Rename / change description |
| DELETE | `/campaigns/{id}` | Delete (409 while it has sessions) |
| GET | `/campaigns/{id}/countries` | Tracked countries (active and removed) with past tags and players |
| POST | `/campaigns/{id}/countries` | Track a country `{tag}` (409 if already tracked) |
| PATCH | `/campaigns/{id}/countries/{tag}` | Set the main player `{player}` (null/empty: use names from saves) |
| DELETE | `/campaigns/{id}/countries/{tag}` | Stop tracking a country (data is kept) |
| GET | `/campaigns/{id}/countries/{tag}` | All metrics, tag and players of a country over time |
| POST | `/campaigns/{id}/reprocess` | Re-extract every save of the campaign → `{queued}` |
| POST | `/campaigns/{id}/sessions` | Create a session and upload saves (multipart, below) |
| GET | `/campaigns/{id}/sessions` | List sessions |
| GET | `/sessions/{id}` | Session details and its saves (`save_list`) |
| POST | `/sessions/{id}/saves` | Add more saves to a session (multipart `files`) |
| DELETE | `/sessions/{id}` | Delete a session, its saves and orphaned files |
| GET | `/sessions/{id}/summary` | Start / end / delta of every metric per country |
| GET | `/saves/{id}` | Save details and processing status |
| POST | `/saves/{id}/reprocess` | Re-extract one save → `{queued}` |
| GET | `/campaigns/{id}/series?metric=&tag=&session=` | Metric over time per country, one point per save |
| GET | `/campaigns/{id}/history?metric=` | Yearly series kept by the game, per country |

`{tag}` and `tag=` accept the current tag, a past tag or the tag the country was added with,
case-insensitively. Metric names are listed in [metrics.md](metrics.md).

## Uploading saves

```bash
curl -F files=@autosave.eu5 -F files=@1445.eu5 -F name="Session 1" -F played_on=2026-11-16 \
     localhost:8000/campaigns/1/sessions
```

`files` is repeatable. `name`, `played_on` (`YYYY-MM-DD`) and `notes` are optional. The response is 202
and comes back before any processing:

```json
{"session_id": 1, "saves": [{"id": 1, "file": "autosave.eu5", "status": "pending", "session_id": 1}]}
```

### Save status

| Status | Meaning |
|---|---|
| `pending` | Queued for the worker |
| `processing` | Being extracted |
| `done` | Stats stored. May carry a `warning` (e.g. the save is from a different playthrough than the rest) |
| `error` | Not an EU5 save, or extraction failed. See `error` |
| `duplicate` | Upload result only: the same file (SHA-256) is already in this campaign. Nothing is added |

Poll `GET /campaigns/{id}` (`saves_pending`, `saves_done`, `saves_error`) or `GET /saves/{id}`.

## Response shapes

These come from the test save. Long lists are cut. [`frontend/src/api/types.ts`](../frontend/src/api/types.ts)
has the full TypeScript types.

`GET /campaigns/1`

```json
{
  "id": 1, "name": "Demo", "description": "Sunday group", "created_at": "2026-11-17T12:20:51+00:00",
  "sessions": 1, "saves": 1, "saves_done": 1, "saves_pending": 0, "saves_error": 0,
  "first_date": "1367.1.1", "last_date": "1367.1.1",
  "countries": ["CAS", "ENG", "FRA", "..."], "main_players": {},
  "latest": {
    "ENG": {"date": "1367.1.1", "tag": "ENG", "country_id": 289, "players": ["Miranda"],
            "metrics": {"gold": 295.30505, "advances": 87.0, "...": "..."}}
  }
}
```

`GET /campaigns/1/series?metric=gold&tag=ENG`: `[game date, value]` pairs per country

```json
{"metric": "gold", "points": {"ENG": [["1367.1.1", 295.30505]]}}
```

`GET /campaigns/1/history?metric=population`: `[year, value]` pairs per country (these go back before the
first save), plus the players seen per country

```json
{
  "metric": "population",
  "series": {"ENG": [[1337, 3015.99041], [1338, 3023.49754], "..."], "...": "..."},
  "players": {"ENG": ["Miranda"], "...": "..."}
}
```

`GET /campaigns/1/countries/ENG`

```json
{
  "tag": "ENG", "country_id": 289,
  "timeline": [
    {"save_id": 1, "session_id": 1, "date": "1367.1.1", "tag": "ENG", "players": ["Miranda"],
     "metrics": {"active_wars": 0.0, "advances": 87.0, "...": "..."}}
  ]
}
```

`GET /sessions/1/summary`

```json
{
  "session_id": 1, "campaign_id": 1, "first_date": "1367.1.1", "last_date": "1367.1.1",
  "countries": {"ENG": {"advances": {"start": 87.0, "end": 87.0, "delta": 0.0}, "...": "..."}},
  "players": {"ENG": ["Miranda"], "...": "..."}
}
```

`GET /campaigns/1/countries`

```json
[{"tag": "ENG", "added_as": "ENG", "country_id": 289, "active": true, "player": null,
  "added_at": "...", "tags": ["ENG"], "players": ["Miranda"], "snapshots": 1, "last_date": "1367.1.1"}]
```

## `POST /decode`

Decodes a save without storing anything (multipart field `file`).

```bash
make decode SAVE=backend/autosave.eu5                              # writes backend/autosave.eu5.json
make decode SAVE=backend/autosave.eu5 PARAMS='sections=metadata'
```

| Parameter | Default | Meaning |
|---|---|---|
| `sections` | all | Comma-separated subset of `header,metadata,gamestate` |
| `select` | – | Comma-separated top-level gamestate keys to keep, e.g. `countries,played_country` (much faster) |
| `dates` | `true` | Render date-like integers as `Y.M.D` strings |
| `strict` | `true` | Fail on unknown value tokens instead of returning a partial result with `errors` |

The response has `header`, `metadata`, `gamestate`, `unknown_tokens` (unresolved native token ids and
how often they appear) and, with `strict=false`, `errors`. A full decode produces JSON several times larger than the
25–40 MB save. Use `select` when you only need a few sections.
