"""Storage and query logic with synthetic statistics (fast, no save files)."""
import pytest

from app.stats.db import Conflict, NotFound, Store
from app.stats.extract import PlayerStats, SaveStats

HOURS_PER_YEAR = 365 * 24


def stats(year: int, players: dict, guid: str = "guid-1", history=()) -> SaveStats:
    return SaveStats(
        playthrough_id=guid, playthrough_name="Test", version="1.4.7",
        game_hours=(5000 + year) * HOURS_PER_YEAR, game_date=f"{year}.1.1",
        players=[PlayerStats(name, i, tag, dict(m)) for i, (name, (tag, m)) in enumerate(players.items())],
        history=list(history),
    )


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "db.sqlite")


def add(store, session_id, sha, s: SaveStats) -> int:
    save_id = store.add_save(session_id, sha, f"{sha}.eu5")["id"]
    store.store_stats(save_id, s)
    return save_id


def test_campaign_crud(store):
    c = store.create_campaign("Camp", "desc")
    assert c["name"] == "Camp" and c["sessions"] == 0
    with pytest.raises(Conflict):
        store.create_campaign("Camp", None)
    assert store.update_campaign(c["id"], "Camp 2", None)["name"] == "Camp 2"
    with pytest.raises(NotFound):
        store.get_campaign(999)
    store.create_session(c["id"], "s1", None, None)
    with pytest.raises(Conflict):
        store.delete_campaign(c["id"])


def test_series_summary_and_overlap(store):
    cid = store.create_campaign("C", None)["id"]
    s1 = store.create_session(cid, "s1", "2026-11-01", None)
    add(store, s1, "a", stats(1337, {"Ana": ("ENG", {"gold": 10}), "Bo": ("FRA", {"gold": 5})}))
    add(store, s1, "b", stats(1338, {"Ana": ("ENG", {"gold": 30}), "Bo": ("FRA", {"gold": 4})}))
    s2 = store.create_session(cid, "s2", "2026-11-08", None)
    # Same game date as the last save of s1 (sessions overlap): the later upload wins.
    add(store, s2, "c", stats(1338, {"Ana": ("ENG", {"gold": 31}), "Bo": ("FRA", {"gold": 4})}))
    add(store, s2, "d", stats(1339, {"Ana": ("GBR", {"gold": 50}), "Bo": ("FRA", {"gold": 1})}))

    series = store.series(cid, "gold")
    assert series["Ana"] == [["1337.1.1", 10], ["1338.1.1", 31], ["1339.1.1", 50]]
    assert store.series(cid, "gold", player="Bo") == {"Bo": [["1337.1.1", 5], ["1338.1.1", 4], ["1339.1.1", 1]]}
    assert store.series(cid, "gold", session_id=s1)["Ana"] == [["1337.1.1", 10], ["1338.1.1", 30]]

    summary = store.session_summary(s1)
    assert (summary["first_date"], summary["last_date"]) == ("1337.1.1", "1338.1.1")
    assert summary["players"]["Ana"]["gold"] == {"start": 10, "end": 30, "delta": 20}

    latest = store.latest_snapshots(cid)
    assert latest["Ana"] == {"date": "1339.1.1", "tag": "GBR", "metrics": {"gold": 50}}

    timeline = store.player_timeline(cid, "Ana")
    assert [t["tag"] for t in timeline] == ["ENG", "ENG", "GBR"]

    sessions = store.list_sessions(cid)
    assert [(s["first_date"], s["last_date"]) for s in sessions] == [("1337.1.1", "1338.1.1"), ("1338.1.1", "1339.1.1")]


def test_history_latest_save_wins(store):
    cid = store.create_campaign("C", None)["id"]
    sid = store.create_session(cid, None, None, None)
    add(store, sid, "a", stats(1338, {"Ana": ("ENG", {})},
                                history=[("ENG", "population", 1337, 1.0), ("ENG", "population", 1338, 2.0)]))
    add(store, sid, "b", stats(1339, {"Ana": ("ENG", {})},
                                history=[("ENG", "population", 1338, 2.5), ("ENG", "population", 1339, 3.0)]))
    h = store.history(cid, "population")
    assert h["series"]["ENG"] == [[1337, 1.0], [1338, 2.5], [1339, 3.0]]
    assert h["players"] == {"ENG": ["Ana"]}


def test_duplicates_warning_and_delete(store):
    cid = store.create_campaign("C", None)["id"]
    s1 = store.create_session(cid, None, None, None)
    add(store, s1, "a", stats(1337, {"Ana": ("ENG", {"gold": 1})}))
    dup = store.add_save(s1, "a", "again.eu5")
    assert dup["status"] == "duplicate"

    s2 = store.create_session(cid, None, None, None)
    other = add(store, s2, "b", stats(1338, {"Ana": ("ENG", {"gold": 2})}, guid="guid-2"))
    assert "guid-2" in store.get_save(other)["warning"]

    # Same file in another campaign is independent.
    cid2 = store.create_campaign("C2", None)["id"]
    s3 = store.create_session(cid2, None, None, None)
    assert store.add_save(s3, "a", "a.eu5")["status"] == "pending"

    orphans = store.delete_session(s1)
    assert orphans == []  # "a" is still used by campaign C2
    assert store.series(cid, "gold") == {"Ana": [["1338.1.1", 2]]}
    store.delete_session(s2)
    assert store.get_campaign(cid)["players"] == []
    store.delete_campaign(cid)
