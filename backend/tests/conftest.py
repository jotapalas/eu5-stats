"""Shared fixtures. `test_save.eu5` can be any EU5 multiplayer save: tests derive their expectations from it.

`mp_facts` reads the save with the low-level decoder only (no `extract`), so extraction can be checked
against an independent reading; API tests compare against `mp_stats` (the extraction output).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SAVES = sorted(
    p for d in (
        ROOT,
        ROOT / "tests" / "fixtures"
    ) for p in d.glob("*.eu5")
)
MP_SAVE = ROOT / "tests" / "fixtures" / "test_save.eu5"
AI_CANDIDATES = 20  # non-played tags tried when looking for an AI country that exists in the save


def pytest_generate_tests(metafunc):
    if "save_path" in metafunc.fixturenames:
        metafunc.parametrize("save_path", SAVES, ids=[p.name for p in SAVES])


def strings_in(obj) -> set[str]:
    """Every string scalar in a decoded tree."""
    out, stack = set(), [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
        elif isinstance(cur, str):
            out.add(cur)
    return out


@dataclass
class SaveFacts:
    metadata_len: int
    played: dict[int, list[str]]  # country id -> player names, from played_country
    tags: dict[int, str]  # country id -> tag, from countries.tags
    meta_strings: set[str]  # string values of the metadata decoded with dates=True


@dataclass
class RefCountry:
    tag: str
    country_id: int
    players: list[str]
    metrics: dict[str, float]


@pytest.fixture(scope="session")
def mp_save_bytes() -> bytes:
    if not MP_SAVE.exists():
        pytest.skip(f"{MP_SAVE.name} not present")
    return MP_SAVE.read_bytes()


@pytest.fixture(scope="session")
def mp_stats(mp_save_bytes):
    from app.eu5.tokens import TokenTable
    from app.stats.extract import extract

    return extract(mp_save_bytes, TokenTable())


@pytest.fixture(scope="session")
def mp_facts(mp_save_bytes) -> SaveFacts:
    from app.eu5.container import open_save
    from app.eu5.decoder import decode_save
    from app.eu5.parser import index_top_level, parse
    from app.eu5.string_lookup import parse_string_lookup
    from app.eu5.tokens import TokenTable
    from app.stats.metrics import as_list

    tokens = TokenTable()
    c = open_save(mp_save_bytes)
    strings = parse_string_lookup(c.string_lookup)
    mv = memoryview(c.gamestate)
    idx = index_top_level(mv, strings, tokens)

    played: dict[int, list[str]] = {}
    for s, e in idx["played_country"]:
        for p in as_list(parse(mv[s:e], strings, tokens)["played_country"]):
            played.setdefault(int(p["country"]), []).append(str(p["name"]))
    (s, e), = idx["countries"]
    raw_tags = parse(mv[s:e], strings, tokens, select={"countries": {"tags": True}})["countries"]["tags"]
    meta = decode_save(mp_save_bytes, sections=("metadata",), tokens=tokens)["metadata"]

    assert len(played) >= 2, "the fixture must be a multiplayer save with at least 2 human countries"
    return SaveFacts(
        metadata_len=c.header.metadata_len,
        played=played,
        tags={int(cid): str(tag) for cid, tag in raw_tags.items()},
        meta_strings=strings_in(meta),
    )


@pytest.fixture(scope="session")
def mp_played(mp_stats) -> list[RefCountry]:
    """Played countries with locations, sorted by tag; [0] is the reference country used by tests."""
    out = []
    for c in sorted((c for c in mp_stats.countries if c.players and c.metrics["locations"] > 0),
                    key=lambda c: c.tag or ""):
        out.append(RefCountry(c.tag, c.country_id, c.players, c.metrics))
    assert len(out) >= 2, "the fixture needs at least 2 human countries with locations"
    return out


@pytest.fixture(scope="session")
def mp_ref(mp_played) -> RefCountry:
    return mp_played[0]


@pytest.fixture(scope="session")
def mp_ai(mp_save_bytes, mp_facts) -> RefCountry:
    """An AI country present in the save (owns locations), found by tracking a few non-played tags."""
    from app.eu5.tokens import TokenTable
    from app.stats.extract import extract

    candidates = sorted({t for cid, t in mp_facts.tags.items() if cid not in mp_facts.played})[:AI_CANDIDATES]
    stats = extract(mp_save_bytes, TokenTable(), [(t, None) for t in candidates])
    for c in sorted(stats.countries, key=lambda c: c.tag or ""):
        if c.country_id not in mp_facts.played and c.metrics["locations"] > 0:
            return RefCountry(c.tag, c.country_id, [], c.metrics)
    pytest.skip("no AI country with locations among the first non-played tags")
