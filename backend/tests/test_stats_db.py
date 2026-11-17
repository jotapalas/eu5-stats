"""Storage and query logic with synthetic statistics (fast, no save files)."""
import pytest

from app.stats.db import Conflict, NotFound, Store
from app.stats.extract import CountryStats, SaveStats

HOURS_PER_YEAR = 365 * 24
IDS = {"ENG": 1, "GBR": 1, "FRA": 2, "CAS": 3, "POR": 4}


def stats(year: int, countries: dict, guid: str = "guid-1", history=()) -> SaveStats:
    """countries: {tag: (players, metrics)}; country ids come from IDS (ENG and GBR are the same country)."""
    return SaveStats(
        playthrough_id=guid, playthrough_name="Test", version="1.4.7",
        game_hours=(5000 + year) * HOURS_PER_YEAR, game_date=f"{year}.1.1",
        countries=[CountryStats(IDS[tag], tag, list(players), dict(m)) for tag, (players, m) in countries.items()],
        history=[(IDS[tag], tag, m, y, v) for tag, m, y, v in history],
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
    assert c["name"] == "Camp" and c["sessions"] == 0 and c["countries"] == []
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
    add(store, s1, "a", stats(1337, {"ENG": (["Ana"], {"gold": 10}), "FRA": (["Bo"], {"gold": 5})}))
    add(store, s1, "b", stats(1338, {"ENG": (["Ana"], {"gold": 30}), "FRA": (["Bo"], {"gold": 4})}))
    s2 = store.create_session(cid, "s2", "2026-11-08", None)
    # Same game date as the last save of s1 (sessions overlap): the later upload wins.
    add(store, s2, "c", stats(1338, {"ENG": (["Ana"], {"gold": 31}), "FRA": (["Bo"], {"gold": 4})}))
    # Another player takes over France; England becomes Great Britain (same country id).
    add(store, s2, "d", stats(1339, {"GBR": (["Ana"], {"gold": 50}), "FRA": (["Cy"], {"gold": 1})}))

    assert store.get_campaign(cid)["countries"] == ["FRA", "GBR"]
    series = store.series(cid, "gold")
    assert series == {"FRA": [["1337.1.1", 5], ["1338.1.1", 4], ["1339.1.1", 1]],
                      "GBR": [["1337.1.1", 10], ["1338.1.1", 31], ["1339.1.1", 50]]}
    # A past tag still finds the country.
    assert store.series(cid, "gold", tag="ENG") == {"GBR": series["GBR"]}
    assert store.series(cid, "gold", session_id=s1)["GBR"] == [["1337.1.1", 10], ["1338.1.1", 30]]
    with pytest.raises(NotFound):
        store.series(cid, "gold", tag="XXX")

    summary = store.session_summary(s1)
    assert (summary["first_date"], summary["last_date"]) == ("1337.1.1", "1338.1.1")
    assert summary["countries"]["GBR"]["gold"] == {"start": 10, "end": 30, "delta": 20}

    latest = store.latest_snapshots(cid)
    assert latest["GBR"] == {"date": "1339.1.1", "tag": "GBR", "country_id": 1, "players": ["Ana"],
                             "metrics": {"gold": 50}}
    assert latest["FRA"]["players"] == ["Cy"]

    t = store.country_timeline(cid, "ENG")
    assert (t["tag"], t["country_id"]) == ("GBR", 1)
    assert [p["tag"] for p in t["timeline"]] == ["ENG", "ENG", "GBR"]
    assert [p["players"] for p in store.country_timeline(cid, "FRA")["timeline"]] == [["Bo"], ["Bo"], ["Cy"]]

    fra = next(c for c in store.list_countries(cid) if c["tag"] == "FRA")
    assert fra["players"] == ["Bo", "Cy"] and fra["snapshots"] == 3 and fra["active"]

    sessions = store.list_sessions(cid)
    assert [(s["first_date"], s["last_date"]) for s in sessions] == [("1337.1.1", "1338.1.1"), ("1338.1.1", "1339.1.1")]


def test_coop_players(store):
    cid = store.create_campaign("C", None)["id"]
    sid = store.create_session(cid, None, None, None)
    save_id = add(store, sid, "a", stats(1337, {"ENG": (["Ana", "Bo"], {"gold": 1})}))
    assert store.latest_snapshots(cid)["ENG"]["players"] == ["Ana", "Bo"]
    save = store.get_save(save_id)
    assert (save["countries"], save["players"]) == (1, 2)


def test_tracked_countries(store):
    cid = store.create_campaign("C", None)["id"]
    sid = store.create_session(cid, None, None, None)
    # An AI country added before any save: resolved by tag when a save is processed.
    store.add_country(cid, "CAS")
    assert store.tracked_countries(cid) == [("CAS", None)]
    with pytest.raises(Conflict):
        store.add_country(cid, "CAS")

    add(store, sid, "a", stats(1337, {"ENG": (["Ana"], {"gold": 1}), "CAS": ([], {"gold": 2})}))
    assert sorted(store.tracked_countries(cid)) == [("CAS", 3), ("ENG", 1)]
    assert store.latest_snapshots(cid)["CAS"]["players"] == []

    # Removing keeps the data, and a played country is not re-added automatically.
    store.remove_country(cid, "ENG")
    with pytest.raises(NotFound):
        store.remove_country(cid, "ENG")
    add(store, sid, "b", stats(1338, {"ENG": (["Ana"], {"gold": 5}), "CAS": ([], {"gold": 3}),
                                      "POR": (["Bo"], {"gold": 9})}))
    assert store.series(cid, "gold", tag="ENG") == {"ENG": [["1337.1.1", 1]]}
    assert store.get_campaign(cid)["countries"] == ["CAS", "POR"]
    assert not next(c for c in store.list_countries(cid) if c["tag"] == "ENG")["active"]

    # Re-adding reactivates it.
    assert store.add_country(cid, "ENG")["active"]
    assert ("ENG", 1) in store.tracked_countries(cid)


def test_add_country_by_current_or_past_tag(store):
    cid = store.create_campaign("C", None)["id"]
    sid = store.create_session(cid, None, None, None)
    add(store, sid, "a", stats(1337, {"ENG": (["Ana"], {})}))
    add(store, sid, "b", stats(1338, {"GBR": (["Ana"], {})}))
    for tag in ("GBR", "ENG"):
        with pytest.raises(Conflict):
            store.add_country(cid, tag)
    assert store.tracked_countries(cid) == [("ENG", 1)]


def test_history_latest_save_wins(store):
    cid = store.create_campaign("C", None)["id"]
    sid = store.create_session(cid, None, None, None)
    add(store, sid, "a", stats(1338, {"ENG": (["Ana"], {})},
                                history=[("ENG", "population", 1337, 1.0), ("ENG", "population", 1338, 2.0)]))
    add(store, sid, "b", stats(1339, {"GBR": (["Bo"], {})},
                                history=[("GBR", "population", 1338, 2.5), ("GBR", "population", 1339, 3.0)]))
    h = store.history(cid, "population")
    assert h["series"]["GBR"] == [[1337, 1.0], [1338, 2.5], [1339, 3.0]]
    assert h["players"] == {"GBR": ["Ana", "Bo"]}


def test_duplicates_warning_and_delete(store):
    cid = store.create_campaign("C", None)["id"]
    s1 = store.create_session(cid, None, None, None)
    add(store, s1, "a", stats(1337, {"ENG": (["Ana"], {"gold": 1})}))
    dup = store.add_save(s1, "a", "again.eu5")
    assert dup["status"] == "duplicate"

    s2 = store.create_session(cid, None, None, None)
    other = add(store, s2, "b", stats(1338, {"ENG": (["Ana"], {"gold": 2})}, guid="guid-2"))
    assert "guid-2" in store.get_save(other)["warning"]

    # Same file in another campaign is independent.
    cid2 = store.create_campaign("C2", None)["id"]
    s3 = store.create_session(cid2, None, None, None)
    assert store.add_save(s3, "a", "a.eu5")["status"] == "pending"

    orphans = store.delete_session(s1)
    assert orphans == []  # "a" is still used by campaign C2
    assert store.series(cid, "gold") == {"ENG": [["1338.1.1", 2]]}
    store.delete_session(s2)
    assert store.series(cid, "gold") == {}
    assert store.get_campaign(cid)["countries"] == ["ENG"]  # the tracked list survives
    store.delete_campaign(cid)
