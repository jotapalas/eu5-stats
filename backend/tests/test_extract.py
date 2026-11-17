"""Statistics extraction on the real fixture save."""
from app.eu5.tokens import TokenTable
from app.stats.extract import extract
from app.stats.metrics import METRICS


def test_metadata(mp_stats):
    assert mp_stats.game_date == "1367.1.5"
    assert mp_stats.playthrough_id == "6d75096e-7442-4df4-966d-60166977abcd"
    assert mp_stats.playthrough_name == "Sweden #b44c1d7d"
    assert mp_stats.version == "1.4.7"


def test_countries(mp_stats):
    countries = {c.tag: c for c in mp_stats.countries}
    assert len(mp_stats.countries) == 14 == len(countries)
    eng = countries["ENG"]
    assert (eng.country_id, eng.players) == (289, ["Miranda"])
    assert eng.metrics["locations"] == 157
    assert countries["SWE"].players == ["jotapalas"]


def test_tracked_countries(mp_save_bytes, mp_stats):
    played = {c.tag for c in mp_stats.countries}
    # By tag (DAN is AI), by id (a played one, deduplicated) and a tag that does not exist.
    stats = extract(mp_save_bytes, TokenTable(), [("DAN", None), ("ignored", 289), ("XXX", None)])
    countries = {c.tag: c for c in stats.countries}
    assert len(stats.countries) == 15 and set(countries) == played | {"DAN"}
    dan = countries["DAN"]
    assert (dan.country_id, dan.players) == (4, []) and dan.metrics["locations"] > 0
    assert {cid for cid, *_ in stats.history} == {c.country_id for c in stats.countries}


def test_all_metrics_numeric(mp_stats):
    names = {m.name for m in METRICS}
    for c in mp_stats.countries:
        assert set(c.metrics) == names, c.tag
        assert all(isinstance(v, float) for v in c.metrics.values()), c.tag
    # Sanity: every country has population, locations and advances.
    assert all(c.metrics["population"] > 0 and c.metrics["locations"] > 0 for c in mp_stats.countries)
    assert all(c.metrics["advances"] > 0 for c in mp_stats.countries)


def test_history(mp_stats):
    eng = sorted((y, v) for _, tag, m, y, v in mp_stats.history if tag == "ENG" and m == "population")
    assert len(eng) == 31
    assert eng[0][0] == 1337 and eng[-1][0] == 1367
    assert {m for _, _, m, _, _ in mp_stats.history} == {"population", "tax_base", "economical_base"}
