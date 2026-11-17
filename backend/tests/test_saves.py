"""Tests against the real saves in the repo (every *.eu5 in backend/ and backend/tests/fixtures).

Only format invariants are asserted, never values specific to one save."""
import orjson
from fastapi.testclient import TestClient

from app.eu5 import lexer as L
from app.eu5.container import open_save
from app.eu5.decoder import decode_save
from app.eu5.parser import index_top_level, parse
from app.eu5.string_lookup import parse_string_lookup
from app.eu5.tokens import TokenTable
from app.main import create_app

EMPTY_TOKENS = TokenTable()  # keep native token keys stable ("0xNNNN") regardless of tokens/eu5.txt


def _find(obj, pred):
    """Yield every scalar in a decoded tree for which pred(value) is true."""
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
        elif pred(cur):
            yield cur


def test_container(save_path):
    data = save_path.read_bytes()
    c = open_save(data)
    assert (c.header.version, c.header.save_type) == (3, 3)
    assert 0 < c.header.metadata_len == len(c.metadata)
    assert c.gamestate and c.string_lookup
    # The gamestate starts with a copy of the metadata block.
    assert c.gamestate[: len(c.metadata)] == c.metadata
    assert len(parse_string_lookup(c.string_lookup)) > 1000


def test_lexer_consumes_metadata(save_path):
    c = open_save(save_path.read_bytes(), with_gamestate=False)
    depth, end = 0, 0
    for off, t, _ in L.iter_tokens(c.metadata):
        depth += (t == L.OPEN) - (t == L.CLOSE)
        assert depth >= 0
        end = off
    assert depth == 0 and end < len(c.metadata)


def test_full_decode(save_path):
    """Strict decode of the whole gamestate: fails on any unknown value token or imbalance."""
    out = decode_save(save_path.read_bytes(), tokens=EMPTY_TOKENS)
    assert "errors" not in out
    gs = out["gamestate"]
    for k in ("current_age", "countries", "provinces", "locations", "played_country", "population"):
        assert k in gs, k
    assert isinstance(gs["current_age"], str) and gs["current_age"].startswith("age_")
    # Every unresolved native token is in the metadata block (the gamestate repeats it once).
    assert all(v % 2 == 0 for v in out["unknown_tokens"].values())
    orjson.dumps(out)  # serialisable


def test_index_top_level(save_path):
    c = open_save(save_path.read_bytes())
    strings = parse_string_lookup(c.string_lookup)
    idx = index_top_level(c.gamestate, strings, EMPTY_TOKENS)
    for k in ("countries", "played_country", "unit_manager", "war_manager"):
        assert k in idx, k
    ranges = sorted(r for rs in idx.values() for r in rs)
    # Non-overlapping, contiguous and covering the whole gamestate.
    assert ranges[0][0] == 0 and ranges[-1][1] == len(c.gamestate)
    assert all(a[1] == b[0] for a, b in zip(ranges, ranges[1:]))


def test_selective_matches_full(mp_save_bytes):
    full = decode_save(mp_save_bytes, sections=("gamestate",), tokens=EMPTY_TOKENS)["gamestate"]
    c = open_save(mp_save_bytes)
    strings = parse_string_lookup(c.string_lookup)
    idx = index_top_level(c.gamestate, strings, EMPTY_TOKENS)
    mv = memoryview(c.gamestate)

    players = [parse(mv[s:e], strings, EMPTY_TOKENS)["played_country"] for s, e in idx["played_country"]]
    assert players == full["played_country"]

    ids = {str(p["country"]): True for p in players}
    (s, e), = idx["countries"]
    part = parse(mv[s:e], strings, EMPTY_TOKENS, select={"countries": {"tags": True, "database": ids}})
    countries = part["countries"]
    assert countries["tags"] == full["countries"]["tags"]
    assert set(countries["database"]) == set(ids)
    for cid in ids:
        country = countries["database"][cid]
        assert country == full["countries"]["database"][cid]
        # `color = rgb { ... }` is a tagged block, so the country record is a dict.
        assert isinstance(country, dict) and "rgb" in country["color"]


def test_mp_metadata_contents(mp_save_bytes, mp_stats):
    out = decode_save(mp_save_bytes, sections=("header", "metadata"), tokens=EMPTY_TOKENS)
    meta = out["metadata"]
    assert list(meta) == ["0x09de"]
    values = set(_find(meta, lambda v: isinstance(v, str)))
    assert mp_stats.game_date in values  # i32 date decoded
    assert mp_stats.version in values
    assert mp_stats.playthrough_id in values


def test_api(mp_save_bytes, mp_facts, tmp_path):
    client = TestClient(create_app(tmp_path, start_worker=False))
    assert client.get("/health").json()["status"] == "ok"

    r = client.post("/decode", params={"sections": "header,metadata"},
                    files={"file": ("save.eu5", mp_save_bytes)})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"header", "metadata", "unknown_tokens"}
    assert body["header"]["metadata_len"] == mp_facts.metadata_len

    r = client.post("/decode", files={"file": ("bad.eu5", b"not a save")})
    assert r.status_code == 422

    r = client.post("/decode", params={"sections": "nope"}, files={"file": ("save.eu5", mp_save_bytes)})
    assert r.status_code == 422

    r = client.post("/decode", files={"file": ("save.eu5", mp_save_bytes)})
    assert r.status_code == 200
    body = orjson.loads(r.content)
    assert {"header", "metadata", "gamestate", "unknown_tokens"} <= set(body)
    assert body["gamestate"]["played_country"]

    r = client.post("/decode", params={"select": "played_country,war_manager"},
                    files={"file": ("save.eu5", mp_save_bytes)})
    assert r.status_code == 200
    assert set(orjson.loads(r.content)["gamestate"]) == {"played_country", "war_manager"}


def test_token_stats(mp_save_bytes, mp_stats):
    from tests.conftest import MP_SAVE
    from tools.token_stats import collect

    stats = collect([MP_SAVE], EMPTY_TOKENS)
    assert stats, "expected unresolved native tokens in the metadata block"
    meta = stats[0x09DE]  # metadata root key
    assert meta["as_key"] >= 1 and meta["path"] == "0x09de"
    date = stats[0x06B5]  # i32 date field in the metadata
    assert date["value_types"]["i32"] >= 1 and mp_stats.game_date in date["sample"]
