"""Extract per-country statistics from a save, parsing only the sections that are needed.

Countries extracted: every country played by a human (`played_country`) plus the countries tracked
by the campaign, given as (tag, country_id or None). A tracked country is looked up by country_id when
known, so it is followed across tag changes (ENG -> GBR keeps the id); otherwise by tag. Tracked
countries missing from the save (not formed yet, annexed) are skipped.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.eu5.container import open_save
from app.eu5.parser import index_top_level, parse
from app.eu5.string_lookup import parse_string_lookup
from app.eu5.tokens import TokenTable
from app.eu5.values import format_date

from .metrics import HISTORY_FIELDS, Context, as_list, compute

# Native tokens in the metadata block (names inferred from their values).
META_ROOT = 0x09DE
META_DATE = 0x06B5
META_PLAYTHROUGH_ID = 0x096E
META_PLAYTHROUGH_NAME = 0x096F
META_VERSION = 0x00EE


class ExtractError(ValueError):
    pass


@dataclass
class CountryStats:
    country_id: int
    tag: str | None
    players: list[str]  # human players controlling the country in this save (empty: AI)
    metrics: dict[str, float]


@dataclass
class SaveStats:
    playthrough_id: str | None
    playthrough_name: str | None
    version: str | None
    game_hours: int  # raw date (hours since -5000.1.1), sortable
    game_date: str  # "1367.1.5"
    countries: list[CountryStats] = field(default_factory=list)
    # (country_id, tag, metric, year, value)
    history: list[tuple[int, str | None, str, int, float]] = field(default_factory=list)


def _section(mv, idx, key, strings, tokens, select=None):
    ranges = idx.get(key)
    if not ranges:
        return None
    s, e = ranges[0]
    return parse(mv[s:e], strings, tokens, select={key: select if select is not None else True})[key]


def extract(data: bytes, tokens: TokenTable | None = None,
            tracked: Iterable[tuple[str, int | None]] = ()) -> SaveStats:
    tokens = tokens or TokenTable.load()
    c = open_save(data)
    strings = parse_string_lookup(c.string_lookup)

    # Metadata (small): parsed with dates=False to keep the raw, sortable date.
    meta_all = parse(c.metadata, strings, tokens, dates=False)
    meta = meta_all.get(tokens.resolve(META_ROOT)) if isinstance(meta_all, dict) else None
    if not isinstance(meta, dict):
        raise ExtractError("Metadata block not found")
    hours = meta.get(tokens.resolve(META_DATE))
    if not isinstance(hours, int):
        raise ExtractError("Save date not found in metadata")

    mv = memoryview(c.gamestate)
    idx = index_top_level(mv, strings, tokens)

    players_raw = []
    for s, e in idx.get("played_country", []):
        players_raw.extend(as_list(parse(mv[s:e], strings, tokens)["played_country"]))
    players_raw = [p for p in players_raw if isinstance(p, dict) and "country" in p and "name" in p]
    if not players_raw:
        raise ExtractError("No human players (played_country) found in the save")
    players: dict[int, list[str]] = {}
    for p in players_raw:
        players.setdefault(int(p["country"]), []).append(str(p["name"]))

    # Two passes over `countries`: tags first (database skipped) to resolve tracked tags, then only
    # the needed database entries.
    tags = (_section(mv, idx, "countries", strings, tokens, {"tags": True}) or {}).get("tags") or {}
    by_tag: dict[str, list[int]] = {}
    for cid, tag in tags.items():
        by_tag.setdefault(str(tag), []).append(int(cid))
    # Candidate country ids for each wanted country, in preference order.
    wanted: list[list[int]] = [[cid] for cid in players]
    for tag, cid in tracked:
        wanted.append([cid] if cid is not None else by_tag.get(tag, []))
    ids = {str(cid): True for cands in wanted for cid in cands}
    database = {}
    if ids:
        database = (_section(mv, idx, "countries", strings, tokens, {"database": ids}) or {}).get("database") or {}

    units = (_section(mv, idx, "unit_manager", strings, tokens) or {}).get("database") or {}
    subunits = (_section(mv, idx, "subunit_manager", strings, tokens) or {}).get("database") or {}
    wars = (_section(mv, idx, "war_manager", strings, tokens) or {}).get("database") or {}

    stats = SaveStats(
        playthrough_id=meta.get(tokens.resolve(META_PLAYTHROUGH_ID)),
        playthrough_name=meta.get(tokens.resolve(META_PLAYTHROUGH_NAME)),
        version=meta.get(tokens.resolve(META_VERSION)),
        game_hours=hours,
        game_date=format_date(hours),
    )
    seen: set[int] = set()
    for cands in wanted:
        cid = next((c for c in cands if isinstance(database.get(str(c)), dict)), None)
        if cid is None or cid in seen:
            continue
        seen.add(cid)
        country = database[str(cid)]
        tag = tags.get(str(cid))
        ctx = Context(country_id=cid, units=units, subunits=subunits, wars=wars)
        stats.countries.append(CountryStats(cid, tag, players.get(cid, []), compute(country, ctx)))

        last_year = country.get("last_stat_year")
        for fld, metric in HISTORY_FIELDS.items():
            series = country.get(fld)
            if not isinstance(series, list) or not isinstance(last_year, int):
                continue
            first_year = last_year - len(series) + 1
            for k, v in enumerate(series):
                if isinstance(v, (int, float)):
                    stats.history.append((cid, tag, metric, first_year + k, float(v)))
    return stats
