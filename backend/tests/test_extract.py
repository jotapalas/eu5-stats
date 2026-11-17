"""Statistics extraction on the real fixture save, checked against an independent reading of it (`mp_facts`)."""
import re

from app.eu5.tokens import TokenTable
from app.stats.extract import extract
from app.stats.metrics import HISTORY_FIELDS, METRICS

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


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


def test_tracked_countries(mp_save_bytes, mp_stats, mp_ref, mp_ai):
    played = {c.country_id for c in mp_stats.countries}
    # By tag (an AI country), by id (a played one, deduplicated) and a tag that does not exist.
    stats = extract(mp_save_bytes, TokenTable(),
                    [(mp_ai.tag, None), ("ignored", mp_ref.country_id), ("XXX", None)])
    by_id = {c.country_id: c for c in stats.countries}
    assert len(by_id) == len(stats.countries) and set(by_id) == played | {mp_ai.country_id}
    ai = by_id[mp_ai.country_id]
    assert (ai.tag, ai.players) == (mp_ai.tag, []) and ai.metrics["locations"] > 0
    assert {cid for cid, *_ in stats.history} == set(by_id)


def test_all_metrics_numeric(mp_stats):
    names = {m.name for m in METRICS}
    for c in mp_stats.countries:
        assert set(c.metrics) == names, c.tag
        assert all(isinstance(v, float) for v in c.metrics.values()), c.tag
    # Sanity: countries that own land have population and advances.
    landed = [c for c in mp_stats.countries if c.metrics["locations"] > 0]
    assert landed and all(c.metrics["population"] > 0 and c.metrics["advances"] > 0 for c in landed)


def test_metrics_match_raw_record(mp_save_bytes, mp_played):
    """Direct-field metrics equal the raw country record, read with the decoder alone."""
    from app.eu5.container import open_save
    from app.eu5.parser import index_top_level, parse
    from app.eu5.string_lookup import parse_string_lookup

    tokens = TokenTable()
    c = open_save(mp_save_bytes)
    strings = parse_string_lookup(c.string_lookup)
    mv = memoryview(c.gamestate)
    (s, e), = index_top_level(mv, strings, tokens)["countries"]
    ids = {str(p.country_id): True for p in mp_played}
    db = parse(mv[s:e], strings, tokens, select={"countries": {"database": ids}})["countries"]["database"]

    def raw(rec, path, default=0):
        for part in path.split("."):
            rec = rec.get(part, default) if isinstance(rec, dict) else default
        return rec

    def size(v):
        return len(v) if isinstance(v, (list, dict)) else (0 if v in (None, 0, "") else 1)

    for p in mp_played:
        rec = db[str(p.country_id)]
        assert p.metrics["locations"] == size(rec.get("owned_locations")), p.tag
        assert p.metrics["advances"] == size(rec.get("researched_advances")), p.tag
        assert p.metrics["gold"] == float(raw(rec, "currency_data.gold")), p.tag
        assert p.metrics["population"] == float(raw(rec, "last_months_population")), p.tag


def test_history(mp_stats, mp_ref):
    assert {m for _, _, m, _, _ in mp_stats.history} == set(HISTORY_FIELDS.values())
    years = mp_ref.history_years
    assert len(years) > 1, "the fixture needs yearly history"
    assert years == list(range(years[0], years[-1] + 1)), "history years must be contiguous and unique"
    assert years[-1] <= int(mp_stats.game_date.split(".")[0])
