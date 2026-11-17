"""Statistics extraction on the real fixture save, checked against an independent reading of it (`mp_facts`)."""
import re

import pytest

from app.eu5.container import open_save
from app.eu5.parser import index_top_level, parse
from app.eu5.string_lookup import parse_string_lookup
from app.eu5.tokens import TokenTable
from app.stats.extract import _civil_wars, _color, _dependencies, _subjects, extract
from app.stats.metrics import METRICS, SERIES_METRICS, VASSAL_METRICS, vassal_metric

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _sections(data: bytes, **select):
    """{key: parsed section} read with the decoder alone, e.g. _sections(data, war_manager=True)."""
    tokens = TokenTable()
    c = open_save(data)
    strings = parse_string_lookup(c.string_lookup)
    mv = memoryview(c.gamestate)
    idx = index_top_level(mv, strings, tokens)
    out = {}
    for key, sel in select.items():
        (s, e), = idx[key]
        out[key] = parse(mv[s:e], strings, tokens, select={key: sel})[key]
    return out


def test_metadata(mp_stats, mp_facts):
    # Extraction reads raw hours (dates=False); the decoder renders dates: both must agree.
    assert re.fullmatch(r"\d+\.\d{1,2}\.\d{1,2}", mp_stats.game_date)
    assert mp_stats.game_date in mp_facts.meta_strings
    assert UUID.match(mp_stats.playthrough_id) and mp_stats.playthrough_id in mp_facts.meta_strings
    assert re.fullmatch(r"\d+\.\d+(\.\d+)*", mp_stats.version) and mp_stats.version in mp_facts.meta_strings
    assert isinstance(mp_stats.playthrough_name, str) and mp_stats.playthrough_name


def test_countries(mp_stats, mp_facts):
    by_id = {c.country_id: c for c in mp_stats.countries}
    assert len(by_id) == len(mp_stats.countries), "duplicate countries"
    assert {cid: c.players for cid, c in by_id.items()} == mp_facts.played
    assert all(c.tag == mp_facts.tags[cid] for cid, c in by_id.items())
    assert any(c.metrics["locations"] > 0 for c in mp_stats.countries)
    assert all(re.fullmatch(r"#[0-9a-f]{6}", c.color or "") for c in mp_stats.countries)


def test_color_rules():
    assert _color({"color": {"rgb": [255, 0, 16]}}) == "#ff0010"
    assert _color({"color": {"rgb": [12.4, 0, 255.0]}}) == "#0c00ff"
    for bad in (None, {}, {"color": [1, 2, 3]}, {"color": {"hsv": [1, 2, 3]}}, {"color": {"rgb": [1, 2]}},
                {"color": {"rgb": [1, 2, 300]}}, {"color": {"rgb": [1, "a", 3]}}):
        assert _color(bad) is None


def test_tracked_countries(mp_save_bytes, mp_stats, mp_ref, mp_ai):
    played = {c.country_id for c in mp_stats.countries}
    # By tag (an AI country), by id (a played one, deduplicated) and a tag that does not exist.
    stats = extract(mp_save_bytes, TokenTable(),
                    [(mp_ai.tag, None), ("ignored", mp_ref.country_id), ("XXX", None)])
    by_id = {c.country_id: c for c in stats.countries}
    assert len(by_id) == len(stats.countries) and set(by_id) == played | {mp_ai.country_id}
    ai = by_id[mp_ai.country_id]
    assert (ai.tag, ai.players) == (mp_ai.tag, []) and ai.metrics["locations"] > 0


def _dep(first, second, kind):
    return {"first": first, "second": second,
            "named_targets": [{"flag": "subject_type", "target": {"type": "subject_type", "object": kind}}]}


def test_subjects_rules():
    children = _dependencies([
        _dep(1, 2, "vassal"), _dep(1, 3, "tributary"), _dep(1, 4, "secessionists"), _dep(1, 5, "fiefdom"),
        _dep(2, 6, "vassal"), _dep(3, 7, "vassal"), _dep(4, 8, "vassal"), _dep(6, 9, "appanage"),
        _dep(6, 10, "secessionists"), _dep(9, 1, "vassal"),  # cycle back to the root
        _dep(5, 11, "hanseatic_member"), {"first": 1, "second": 12},  # no subject type: ignored
        _dep(1, 2, "vassal"),  # repeated entry
    ])
    assert _subjects(children, 1, all_levels=False) == [2, 5]
    assert sorted(_subjects(children, 1, all_levels=True)) == [2, 5, 6, 9]
    assert _subjects(children, 99, all_levels=True) == []
    assert _dependencies(_dep(1, 2, "vassal")) == {1: [(2, "vassal")]}  # single entry written bare


def test_civil_wars_rules():
    wars = {
        "1": {"has_civil_war": True, "original_attacker": 10, "original_attacker_target": 1},
        "2": {"has_civil_war": True, "original_attacker": 11, "original_attacker_target": 1},
        "3": {"has_civil_war": True, "original_attacker": 12, "original_attacker_target": 2, "end_date": "1350.1.1"},
        "4": {"revolt": None, "original_attacker": 13, "original_attacker_target": 3},  # independence war
        "5": {"original_attacker": 14, "original_attacker_target": 4},  # normal war
        "6": "none",
    }
    assert _civil_wars(wars) == {1: [10, 11]}


def test_all_metrics_numeric(mp_stats):
    names = {m.name for m in METRICS} | SERIES_METRICS
    for c in mp_stats.countries:
        assert set(c.metrics) == names, c.tag
        assert all(isinstance(v, float) for v in c.metrics.values()), c.tag
    # Sanity: countries that own land have population and advances.
    landed = [c for c in mp_stats.countries if c.metrics["locations"] > 0]
    assert landed and all(c.metrics["population"] > 0 and c.metrics["advances"] > 0 for c in landed)


def test_vassal_aggregates(mp_save_bytes):
    # Every AI country with vassals (first 20), to exercise the aggregation on real data.
    deps = _sections(mp_save_bytes, diplomacy_manager={"dependency": True})["diplomacy_manager"]["dependency"]
    children = _dependencies(deps)
    overlords = [cid for cid in children if _subjects(children, cid, all_levels=False)][:20]
    stats = extract(mp_save_bytes, TokenTable(), [("", cid) for cid in overlords])
    assert any(c.metrics["vassals"] > 0 for c in stats.countries)
    for c in stats.countries:
        assert c.metrics["vassals"] <= c.metrics["all_vassals"], c.tag
        for name in VASSAL_METRICS:
            own, direct, every = (c.metrics[name], c.metrics[vassal_metric(name, "direct")],
                                  c.metrics[vassal_metric(name, "all")])
            assert own <= direct <= every, (c.tag, name)
        if c.metrics["vassals"] == 0:
            assert all(c.metrics[vassal_metric(n, "direct")] == c.metrics[n] for n in VASSAL_METRICS), c.tag


def test_civil_war_land(mp_save_bytes):
    """A government in a civil war keeps counting the land held by the faction."""
    wars = _sections(mp_save_bytes, war_manager=True)["war_manager"]["database"]
    rebels_of = _civil_wars(wars)
    if not rebels_of:
        pytest.skip("no active civil war in the fixture save")
    governments = list(rebels_of)[:10]
    ids = {str(i): True for g in governments for i in [g, *rebels_of[g]]}
    db = _sections(mp_save_bytes, countries={"database": ids})["countries"]["database"]
    stats = extract(mp_save_bytes, TokenTable(), [("", g) for g in governments])
    by_id = {c.country_id: c for c in stats.countries}

    def size(v):
        return len(v) if isinstance(v, (list, dict)) else (0 if v in (None, 0, "") else 1)

    checked = 0
    for g in governments:
        rec, factions = db.get(str(g)), [db[str(r)] for r in rebels_of[g] if isinstance(db.get(str(r)), dict)]
        if not isinstance(rec, dict) or g not in by_id or not factions:
            continue
        m = by_id[g].metrics
        own_provinces = size(rec.get("provinces"))
        assert m["locations"] == size(rec.get("owned_locations")) + sum(size(f.get("owned_locations")) for f in factions)
        assert own_provinces <= m["provinces"] <= own_provinces + sum(size(f.get("provinces")) for f in factions)
        assert m["population"] >= float(rec.get("last_months_population", 0))
        assert m["core_locations"] == size(rec.get("core_locations"))  # not affected by civil wars
        checked += 1
    assert checked


def test_metrics_match_raw_record(mp_save_bytes, mp_played):
    """Direct-field metrics equal the raw country record, read with the decoder alone."""
    rebels_of = _civil_wars(_sections(mp_save_bytes, war_manager=True)["war_manager"]["database"])
    ids = {str(p.country_id): True for p in mp_played}
    db = _sections(mp_save_bytes, countries={"database": ids})["countries"]["database"]

    def raw(rec, path, default=0):
        for part in path.split("."):
            rec = rec.get(part, default) if isinstance(rec, dict) else default
        return rec

    def size(v):
        return len(v) if isinstance(v, (list, dict)) else (0 if v in (None, 0, "") else 1)

    for p in mp_played:
        rec = db[str(p.country_id)]
        assert p.metrics["advances"] == size(rec.get("researched_advances")), p.tag
        assert p.metrics["gold"] == float(raw(rec, "currency_data.gold")), p.tag
        if p.country_id in rebels_of:  # CIVIL_WAR_METRICS corrected, see test_civil_war_land
            continue
        assert p.metrics["locations"] == size(rec.get("owned_locations")), p.tag
        assert p.metrics["population"] == float(raw(rec, "last_months_population")), p.tag
