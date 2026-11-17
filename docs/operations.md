# Operations

Running the service, loading a campaign's saves, keeping the data safe, and publishing the read-only
site.

## Running

Everything runs in Docker Compose. `make help` lists every target.

```bash
make build         # build the images (the API image includes test dependencies)
make up            # API on http://localhost:8000, web UI on http://localhost:5173
make logs          # all services (backend-logs / web-logs for one)
make down          # stop everything
```

| Service | Port | What |
|---|---|---|
| `api` | 8000 | FastAPI + background worker. `./backend` is mounted at `/app` |
| `web` | 5173 | Vite dev server with hot reload. Proxies `/api` to `api` |
| `web-prod` (profile `prod`) | 8080 | nginx serving the built SPA and proxying `/api` (`make web-build`, `make web-prod-up`) |

The `api` container only sees `backend/` (plus `docs/` and `frontend/src/` for `make docs`). Paths
given to container commands are relative to `backend/`. For example, put saves you want to decode or
scan with `token-stats` in `backend/` or `backend/saves/`.

### Without Docker

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload            # http://localhost:8000

cd ../frontend
npm install && API_URL=http://localhost:8000 npm run dev
```

Data goes to `backend/data/` by default (in Docker, the same folder through the mount). Set
`EU5_DATA_DIR` to put it elsewhere.

## Loading a campaign

You can do all of this from the web UI (**Sesiones → Subir sesión**). The command line equivalent:

```bash
make campaign NAME="Sweden MP" DESC="Sunday group"                 # -> {"id": 1, ...}
make session CAMPAIGN=1 DIR=~/saves/session1 NAME="Session 1" PLAYED_ON=2026-11-16
curl localhost:8000/campaigns/1                                    # saves_pending / saves_done / saves_error
```

`make session` uploads every `*.eu5` in `DIR`. A useful convention is one save per in-game year: the
charts get one point per save. Processing takes a few seconds per save and runs one save at a time.

Things to know:

- **Duplicates**: the same file uploaded twice to a campaign is reported as `duplicate` and ignored.
- **Same in-game date**: when two saves have the same date (autosave and manual save), the most recently
  uploaded one is used for campaign-wide views.
- **Wrong playthrough**: a save from a different game is still processed but gets a `warning`. Delete
  its session if it was a mistake.
- **Tracked countries**: countries played by humans are added automatically. Add AI countries in
  **Ajustes** or with `POST /campaigns/{id}/countries {"tag": "DAN"}`. Changes apply to saves processed
  afterwards. Reprocess to apply them to existing saves.
- **Main player**: when several people played a country, set the name to show in **Ajustes** (or with
  `PATCH /campaigns/{id}/countries/{tag}`).

### Reprocessing

After changing tracked countries or upgrading the extraction code (new metrics, fixes):

```bash
make reprocess CAMPAIGN=1          # whole campaign (POST /campaigns/{id}/reprocess)
```

A single save can be reprocessed from its session page (**Reprocesar**) or with
`POST /saves/{id}/reprocess`.

Reprocessing uses the *current* tracked list. A country removed from the list loses its rows in the
reprocessed saves.

## Data and backups

```
backend/data/
  eu5stats.db         SQLite (WAL: also eu5stats.db-wal / -shm while running)
  uploads/<sha256>.eu5  every uploaded save, shared across campaigns
```

`data/` is git-ignored. **`uploads/` is the source of truth**: everything in the database can be
recomputed from it. To back up, stop the stack (`make down`) and copy the whole `data/` folder.

The database has no migrations. After a schema change, either the code migrates it in `Store.__init__`,
or you delete `eu5stats.db`, restart, re-create the campaigns and re-upload the saves (the files in
`uploads/` are reused). `make db-shell` opens `sqlite3` on the database.

Upload size is not limited and the API has no authentication or CORS. Do not expose port 8000 to the
internet. Share results through the read-only site instead.

## Publishing the read-only site (Cloudflare Pages)

Saves are processed and managed on your machine. A static, read-only copy of the statistics is
published. No server or database runs in the cloud, so **publish again after uploading new saves**.

```bash
make public-build                 # frontend/dist-public: read-only build + data/*.json (CAMPAIGN=<id> for one)
make public-preview               # check it on http://localhost:4173 (PREVIEW_PORT=...)
make public-preview-stop
make publish                      # public-build + deploy with wrangler
```

`make publish` needs a `.env` in the repo root (git-ignored):

```
CLOUDFLARE_API_TOKEN=...          # permission "Cloudflare Pages: Edit"
CLOUDFLARE_ACCOUNT_ID=...
```

The Pages project defaults to `eu5-stats` (`PAGES_PROJECT=...`). The free plan allows 20,000 files and
25 MiB per file. A 500-year campaign is roughly 110 files and 12 MB.

The read-only build hides uploads, settings, delete and reprocess. Everything else works the same as
locally.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Save stuck in `pending` | The worker processes one save at a time. Check `make backend-logs` |
| `error: Not an EU5 save` | The file is not a binary `.eu5` save (e.g. a text/debug save or a different game) |
| `error: Unknown EU5 value token 0x0dXX` | A game update added a value type. See [development.md](development.md#new-value-token) |
| A country is missing | It is not played by a human and not tracked. Add it and reprocess |
| Country shows an old date in Ranking | It no longer exists in the latest save (annexed), so its last known values are shown |
