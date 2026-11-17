"""Export every read-only API response to static JSON files, for the public read-only frontend.

The files mirror the GET endpoints the frontend reads, with identical content (built with the same
`Store` methods). The frontend compiled with VITE_READONLY=1 maps API paths to these files
(`staticPath` in frontend/src/api/client.ts); keep both in sync when a read endpoint is added.

  data/metrics.json                              /metrics
  data/campaigns.json                            /campaigns
  data/campaigns/{id}.json                       /campaigns/{id}
  data/campaigns/{id}/series/{metric}.json       /campaigns/{id}/series?metric=
  data/campaigns/{id}/history/{metric}.json      /campaigns/{id}/history?metric=
  data/campaigns/{id}/countries/{TAG}.json       /campaigns/{id}/countries/{TAG}
  data/campaigns/{id}/sessions.json              /campaigns/{id}/sessions
  data/sessions/{sid}.json                       /sessions/{sid}
  data/sessions/{sid}/summary.json               /sessions/{sid}/summary

Usage: python -m tools.export_static OUT_DIR [--campaign ID ...] [--db data/eu5stats.db]
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import orjson

from app.stats.api import HISTORY_METRICS, list_metrics
from app.stats.db import Store
from app.stats.metrics import METRICS


def export(store: Store, out: Path, campaign_ids: list[int] | None = None) -> dict[str, int]:
    """Write the files under out/data (replacing it). Returns {"files": n, "bytes": total}."""
    data = out / "data"
    if data.exists():
        shutil.rmtree(data)  # no leftovers from deleted campaigns/sessions
    stats = {"files": 0, "bytes": 0}

    def write(rel: str, obj) -> None:
        path = data / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = orjson.dumps(obj)
        path.write_bytes(raw)
        stats["files"] += 1
        stats["bytes"] += len(raw)

    campaigns = store.list_campaigns()
    if campaign_ids is not None:
        campaigns = [c for c in campaigns if c["id"] in campaign_ids]
    write("metrics.json", list_metrics())
    write("campaigns.json", campaigns)

    for c in campaigns:
        cid = c["id"]
        detail = store.get_campaign(cid)
        detail["latest"] = store.latest_snapshots(cid)
        write(f"campaigns/{cid}.json", detail)
        for m in METRICS:
            write(f"campaigns/{cid}/series/{m.name}.json",
                  {"metric": m.name, "points": store.series(cid, m.name)})
        for name in HISTORY_METRICS:
            write(f"campaigns/{cid}/history/{name}.json", {"metric": name, **store.history(cid, name)})
        for tag in sorted(set(detail["latest"]) | set(detail["countries"])):
            try:
                write(f"campaigns/{cid}/countries/{tag}.json", store.country_timeline(cid, tag))
            except LookupError:  # tracked but never seen in a processed save
                pass
        sessions = store.list_sessions(cid)
        write(f"campaigns/{cid}/sessions.json", sessions)
        for s in sessions:
            write(f"sessions/{s['id']}.json", store.get_session(s["id"]))
            write(f"sessions/{s['id']}/summary.json", store.session_summary(s["id"]))
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path, help="output directory (files go to OUT/data)")
    ap.add_argument("--campaign", type=int, action="append", help="campaign id to export (default: all)")
    ap.add_argument("--db", type=Path, default=Path("data/eu5stats.db"))
    args = ap.parse_args(argv)
    if not args.db.exists():
        print(f"Database not found: {args.db}", file=sys.stderr)
        return 1
    stats = export(Store(args.db), args.out, args.campaign)
    print(f"Exported {stats['files']} files, {stats['bytes'] / 1e6:.1f} MB to {args.out / 'data'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
