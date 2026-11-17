"""Static export: files mirror the read endpoints (synthetic data, no save files)."""
import orjson

from app.stats.db import Store
from app.stats.extract import CountryStats, SaveStats
from app.stats.metrics import SERIES_METRICS
from tools.export_static import export

HOURS_PER_YEAR = 365 * 24


def stats(year: int, countries: dict) -> SaveStats:
    """countries: {tag: (country_id, players, metrics)}."""
    return SaveStats(
        playthrough_id="g", playthrough_name="T", version="1.4.7",
        game_hours=(5000 + year) * HOURS_PER_YEAR, game_date=f"{year}.1.1",
        countries=[CountryStats(cid, tag, players, m) for tag, (cid, players, m) in countries.items()],
    )


def load(out, rel):
    return orjson.loads((out / "data" / rel).read_bytes())


def test_export_mirrors_store(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    cid = store.create_campaign("C", None)["id"]
    other = store.create_campaign("Other", None)["id"]
    sid = store.create_session(cid, "s1", None, None)
    for sha, year in (("a", 1337), ("b", 1338)):
        save_id = store.add_save(sid, sha, f"{sha}.eu5")["id"]
        store.store_stats(save_id, stats(year, {"ENG": (1, ["Ana"], {"gold": year - 1330}),
                                                "FRA": (2, ["Bo"], {"gold": 1})}))
    store.set_country_player(cid, "ENG", "Main")

    out = tmp_path / "site"
    (out / "data" / "stale").mkdir(parents=True)  # leftovers are removed
    result = export(store, out, [cid])

    assert not (out / "data" / "stale").exists()
    assert [c["id"] for c in load(out, "campaigns.json")] == [cid]  # filtered
    assert not (out / "data" / "campaigns" / f"{other}.json").exists()

    camp = load(out, f"campaigns/{cid}.json")
    assert camp["main_players"] == {"ENG": "Main"} and set(camp["latest"]) == {"ENG", "FRA"}
    assert load(out, f"campaigns/{cid}/series/gold.json") == {
        "metric": "gold", "points": store.series(cid, "gold")}
    assert len(list((out / "data" / "campaigns" / str(cid) / "series").iterdir())) == len(SERIES_METRICS)
    assert load(out, f"campaigns/{cid}/countries/ENG.json") == store.country_timeline(cid, "ENG")
    assert [s["id"] for s in load(out, f"campaigns/{cid}/sessions.json")] == [sid]
    assert load(out, f"sessions/{sid}.json")["save_list"][0]["file_name"] == "a.eu5"
    assert load(out, f"sessions/{sid}/summary.json")["countries"]["ENG"]["gold"]["delta"] == 1
    assert "metrics" in load(out, "metrics.json")
    assert result["files"] == len(list(p for p in (out / "data").rglob("*.json")))
