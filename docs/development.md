# Development

Read [architecture.md](architecture.md) first. [save-format.md](save-format.md) covers the decoder.

## Setup

```bash
make build && make up        # API on :8000 (no reload: `docker compose restart api`), Vite on :5173 (hot reload)
make test                    # pytest in the api container
make test ARGS="tests/test_units.py -x"
make web-lint                # tsc + eslint
make web-test                # vitest
make docs                    # regenerate docs/metrics.md
make shell / make web-shell  # shell in the api / web container
```

Python ≥ 3.12. Dependencies are minimal on purpose: `fastapi`, `uvicorn`, `python-multipart`, `orjson`
(+ `pytest`, `httpx` for tests). No ORM, no linter.

On Windows with the repo on WSL, git needs `git -c safe.directory='*' ...`. Run `make` and Python
inside WSL.

## Tests

| File | What | Needs the real save |
|---|---|---|
| `test_units.py` | Decoder logic on synthetic token streams (`tok`, `key`, `i32`, `run` helpers). Fast | no |
| `test_stats_db.py` | `Store` queries on synthetic `SaveStats` (`stats(year, {...})` helper) | no |
| `test_metrics_doc.py` | `docs/metrics.md` is up to date, every metric has a Spanish label | no |
| `test_export_static.py` | Static export for the read-only site mirrors the `Store` | no |
| `test_saves.py` | Every `*.eu5` in `backend/` and `backend/tests/fixtures/` decodes | yes |
| `test_extract.py`, `test_stats_api.py` | Extraction and the API flow on `tests/fixtures/test_save.eu5` | yes |

`*.eu5` is git-ignored, so **the fixture is not in the repo**. Copy **any EU5 multiplayer save** with at
least 2 human countries to `backend/tests/fixtures/test_save.eu5`. Without it those tests are skipped.

Tests never hardcode values from a particular save. Fixtures in `conftest.py` derive them:

- `mp_facts`: players, tags, metadata strings and header, read with the low-level decoder only. Extraction
  is checked against it.
- `mp_stats`: the `extract()` output. The API tests compare against it.
- `mp_played` / `mp_ref` (played countries sorted by tag, the first one is the reference) and `mp_ai` (an
  AI country that exists in the save).

Use these instead of literals when you add assertions. Format invariants true of every EU5 save (header
`(3, 3)`, metadata repeated in the gamestate, `0x09de` root key) are fine to assert directly.
Full-decode tests take a while (25–40 MB saves).

- API tests use `create_app(tmp_path, start_worker=False)` and run `app.state.ingestor.process_pending()`
  instead of the worker thread.
- Tests use an empty `TokenTable()`, so keys stay `"0xNNNN"`. Never make tests depend on
  `tokens/eu5.txt`.
- Importing `app.main` builds the module-level app, which opens `data/eu5stats.db` unless
  `EU5_DATA_DIR` points elsewhere.

## Recipes

### New metric

1. Append a `Metric(name, category, description, fn)` to `METRICS` in
   [`metrics.py`](../backend/app/stats/metrics.py). `fn(country, ctx)` must return a `float` and default
   to 0 for missing fields (use `get`, `num`, `count`, `as_list`, `_field`, `_len`).
2. If it needs data outside the country record, parse that section in `extract.py` with a `select` as
   narrow as possible and add a field to `Context`.
3. Add the Spanish label to `METRIC_LABELS` in `frontend/src/i18n.ts`. If lower is better, add it to
   `LOWER_IS_BETTER` in `frontend/src/lib/format.ts` (and to `RANK_METRICS` if it is a rank).
4. If it should also be summed over vassals, add it to `VASSAL_METRICS`; the `__vassals` /
   `__all_vassals` variants and the UI selector follow. If it measures land that a civil war faction can
   hold, add it to `CIVIL_WAR_METRICS` and handle it in `extract.with_rebels`.
5. `make docs`, `make test`.
6. Existing campaigns need `make reprocess CAMPAIGN=<id>`.

### New value token

A game update can add a value type. Decoding then fails with `Unknown EU5 value token 0x0dXX`.

1. Find its payload size from real saves (`make decode ... strict=false` shows where it fails).
2. Add the constant to `lexer.py` (`KNOWN` and `iter_tokens`).
3. Add its payload size to `_build_size_table` and its decoding to `scalar()` in `parser.py`.
4. Add its type name to `TYPE_NAMES` in `tools/token_stats.py`.
5. Add a synthetic test in `tests/test_units.py` and update [save-format.md](save-format.md).

### Naming native tokens

Add `<id> <name>` lines to `backend/tokens/eu5.txt`. `make token-stats` (or `ARGS=--json`) shows unresolved
ids with counts, value types, a sample value and the first path where each appeared.

### New endpoint

Add it to `app/stats/api.py` (or `main.py` for decoder-level endpoints) and put the SQL in a `Store`
method. Raise `NotFound` / `Conflict` from `db.py`, which map to 404 / 409. Do not raise `HTTPException`
there. Test it in `test_stats_api.py` (real save) or `test_stats_db.py` (synthetic). Then document it in
[api.md](api.md).

If the UI reads it, update `frontend/src/api/types.ts`, add a hook in `hooks.ts`, and add the path to
`tools/export_static.py` and `staticPath` in `client.ts` (+ its test) so the read-only site has it.

### New view

Page in `frontend/src/pages/`, route in `App.tsx`, tab in `CampaignLayout` `TABS` if needed, data hook in
`hooks.ts`. All UI text goes in Spanish. Campaign-scoped query keys start with `["campaign", id]`.

### Schema change

Edit `SCHEMA` in `db.py`. `CREATE TABLE IF NOT EXISTS` does not alter existing databases. Either add an
explicit `ALTER TABLE` in `Store.__init__` or document that `data/eu5stats.db` must be rebuilt
([operations.md](operations.md#data-and-backups)).

## Conventions

- Code, comments, docstrings and identifiers in English. UI text in Spanish.
- Every Python module starts with a docstring and `from __future__ import annotations`. Format discoveries
  go in module docstrings and [save-format.md](save-format.md).
- Modern typing (`dict[str, int]`, `X | None`), `@dataclass` records, UPPER_CASE module constants.
- Raw SQL with named or `?` parameters. Use f-strings only for trusted fragments like `EFFECTIVE_SAVES`.
- `parser.parse`, `skip_*` and `index_top_level` are micro-optimised. Keep that style.
- Frontend colours: the game's country colours plus per-campaign overrides (`src/lib/colors.ts`). Clashes
  are told apart by dash pattern, never by generating new hues.
- Comments are terse and explain *why*. Lines up to ~110 chars.
