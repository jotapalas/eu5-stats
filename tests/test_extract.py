"""Statistics extraction on the real fixture save."""
from app.stats.metrics import METRICS


def test_metadata(mp_stats):
    assert mp_stats.game_date == "1367.1.5"
    assert mp_stats.playthrough_id == "6d75096e-7442-4df4-966d-60166977abcd"
    assert mp_stats.playthrough_name == "Sweden #b44c1d7d"
    assert mp_stats.version == "1.4.7"


def test_players(mp_stats):
    players = {p.name: p for p in mp_stats.players}
    assert len(mp_stats.players) == 14 == len(players)
    eng = players["Miranda"]
    assert (eng.country_id, eng.tag) == (289, "ENG")
    assert eng.metrics["locations"] == 157
    assert players["jotapalas"].tag == "SWE"


def test_all_metrics_numeric(mp_stats):
    names = {m.name for m in METRICS}
    for p in mp_stats.players:
        assert set(p.metrics) == names, p.name
        assert all(isinstance(v, float) for v in p.metrics.values()), p.name
    # Sanity: every player has population, locations and advances.
    assert all(p.metrics["population"] > 0 and p.metrics["locations"] > 0 for p in mp_stats.players)
    assert all(p.metrics["advances"] > 0 for p in mp_stats.players)


def test_history(mp_stats):
    eng = sorted((y, v) for tag, m, y, v in mp_stats.history if tag == "ENG" and m == "population")
    assert len(eng) == 31
    assert eng[0][0] == 1337 and eng[-1][0] == 1367
    assert {m for _, m, _, _ in mp_stats.history} == {"population", "tax_base", "economical_base"}
