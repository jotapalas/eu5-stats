"""Extract per-country statistics from a save, parsing only the sections that are needed.

Countries extracted: every country played by a human (`played_country`) plus the countries tracked
by the campaign, given as (tag, country_id or None). A tracked country is looked up by country_id when
known, so it is followed across tag changes (ENG -> GBR keeps the id); otherwise by tag. Tracked
countries missing from the save (not formed yet, annexed) are skipped.

Subjects live in `diplomacy_manager.dependency`: a list of `{first: overlord id, second: subject id,
named_targets: [{flag: subject_type, target: {type: subject_type, object: <type>}}], start_date, seed}`.
Types seen: vassal, fiefdom, dominion, appanage, tusi, taifa, maha_samanta, tributary, hanseatic_member,
secessionists. Subjects nest (vassals of vassals). For VASSAL_METRICS each country also gets
`<metric>__vassals` (own + direct vassals) and `<metric>__all_vassals` (own + vassals at every level).
EXCLUDED_SUBJECTS are ignored with their subtree. `secessionists` is excluded because its `first` is the
country backing a rebel province (bornu_province rebels against KAN, listed under KBO), not its victim.

Civil wars: `war_manager.database` entries without `end_date` and with `has_civil_war` are fought by a
faction country (`original_attacker`, e.g. CIVILWAR_FACTION_nobles_estate) against its own government
(`original_attacker_target`). The faction holds part of the government's land only temporarily, so while
the war lasts that land still counts for the government (CIVIL_WAR_METRICS). Provinces are per-owner
objects (`provinces.database[id].province_definition`) and a faction may hold part of a province, so the
province count is the union of definitions. Independence wars are not treated this way: a rebelling
subject is no longer a subject, and that loss is real.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.eu5.container import open_save
from app.eu5.parser import index_top_level, parse
from app.eu5.string_lookup import parse_string_lookup
from app.eu5.tokens import TokenTable
from app.eu5.values import format_date

from .metrics import (
    CIVIL_WAR_METRICS,
    EXCLUDED_SUBJECTS,
    VASSAL_METRICS,
    Context,
    as_list,
    compute,
    vassal_metric,
)

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


def _section(mv, idx, key, strings, tokens, select=None):
    ranges = idx.get(key)
    if not ranges:
        return None
    s, e = ranges[0]
    return parse(mv[s:e], strings, tokens, select={key: select if select is not None else True})[key]


def _dependencies(deps) -> dict[int, list[tuple[int, str]]]:
    """overlord id -> [(subject id, subject type)] from diplomacy_manager.dependency."""
    children: dict[int, list[tuple[int, str]]] = {}
    for d in as_list(deps):
        if not isinstance(d, dict) or not isinstance(d.get("first"), int) or not isinstance(d.get("second"), int):
            continue
        kind = None
        for nt in as_list(d.get("named_targets")):
            if isinstance(nt, dict) and nt.get("flag") == "subject_type" and isinstance(nt.get("target"), dict):
                kind = nt["target"].get("object")
        if isinstance(kind, str):  # entries without a subject type are not subjects
            children.setdefault(d["first"], []).append((d["second"], kind))
    return children


def _subjects(children: dict[int, list[tuple[int, str]]], cid: int, all_levels: bool) -> list[int]:
    """Vassals of `cid`: direct ones or, with all_levels, vassals at every level.

    Excluded types are skipped with their subtree.
    """
    vassals: list[int] = []
    seen = {cid}
    stack = [cid]
    while stack:
        for sid, kind in children.get(stack.pop(), ()):
            if sid in seen or kind in EXCLUDED_SUBJECTS:
                continue
            seen.add(sid)
            vassals.append(sid)
            if all_levels:
                stack.append(sid)
    return vassals


def _civil_wars(wars: dict) -> dict[int, list[int]]:
    """Government id -> faction ids it is fighting in active civil wars."""
    rebels: dict[int, list[int]] = {}
    for w in wars.values():
        if not isinstance(w, dict) or "end_date" in w or not w.get("has_civil_war"):
            continue
        faction, government = w.get("original_attacker"), w.get("original_attacker_target")
        if isinstance(faction, int) and isinstance(government, int) and faction != government:
            rebels.setdefault(government, []).append(faction)
    return rebels


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
    # the needed database entries (wanted countries, their subjects and civil war factions).
    tags = (_section(mv, idx, "countries", strings, tokens, {"tags": True}) or {}).get("tags") or {}
    by_tag: dict[str, list[int]] = {}
    for cid, tag in tags.items():
        by_tag.setdefault(str(tag), []).append(int(cid))
    # Candidate country ids for each wanted country, in preference order.
    wanted: list[list[int]] = [[cid] for cid in players]
    for tag, cid in tracked:
        wanted.append([cid] if cid is not None else by_tag.get(tag, []))

    deps = (_section(mv, idx, "diplomacy_manager", strings, tokens, {"dependency": True}) or {}).get("dependency")
    children = _dependencies(deps)
    wars = (_section(mv, idx, "war_manager", strings, tokens) or {}).get("database") or {}
    rebels_of = _civil_wars(wars)

    needed = {cid for cands in wanted for cid in cands}
    needed |= {s for cid in list(needed) for s in _subjects(children, cid, all_levels=True)}
    needed |= {r for cid in list(needed) for r in rebels_of.get(cid, ())}
    database = {}
    if needed:
        database = (_section(mv, idx, "countries", strings, tokens,
                              {"database": {str(i): True for i in needed}}) or {}).get("database") or {}

    subunits = (_section(mv, idx, "subunit_manager", strings, tokens) or {}).get("database") or {}

    def record(cid: int) -> dict | None:
        rec = database.get(str(cid))
        return rec if isinstance(rec, dict) else None

    def rebels(cid: int) -> list[int]:
        return [r for r in rebels_of.get(cid, ()) if record(r)]

    # Province definitions, only for governments in a civil war and their factions.
    in_civil_war = [cid for cid in needed if record(cid) and rebels(cid)]
    province_ids = {str(p) for cid in in_civil_war for x in [cid, *rebels(cid)]
                    for p in as_list(record(x).get("provinces"))}
    provinces = {}
    if province_ids:
        provinces = (_section(mv, idx, "provinces", strings, tokens, {"database": {
            p: {"province_definition": True} for p in province_ids}}) or {}).get("database") or {}

    def with_rebels(cid: int, metrics: dict[str, float]) -> dict[str, float]:
        """Count the land held by civil war factions as the government's (CIVIL_WAR_METRICS)."""
        factions = rebels(cid)
        if not factions:
            return metrics
        for name in CIVIL_WAR_METRICS:
            if name == "provinces":
                defs = set()
                for x in [cid, *factions]:
                    for p in as_list(record(x).get("provinces")):
                        prov = provinces.get(str(p))
                        defs.add(prov.get("province_definition", p) if isinstance(prov, dict) else p)
                metrics[name] = float(len(defs))
            else:
                metrics[name] += sum(compute(record(r), Context(r), (name,))[name] for r in factions)
        return metrics

    stats = SaveStats(
        playthrough_id=meta.get(tokens.resolve(META_PLAYTHROUGH_ID)),
        playthrough_name=meta.get(tokens.resolve(META_PLAYTHROUGH_NAME)),
        version=meta.get(tokens.resolve(META_VERSION)),
        game_hours=hours,
        game_date=format_date(hours),
    )

    subject_cache: dict[int, dict[str, float]] = {}

    def subject_metrics(sid: int) -> dict[str, float]:
        if sid not in subject_cache:
            rec = record(sid)
            subject_cache[sid] = (with_rebels(sid, compute(rec, Context(sid, subunits=subunits, wars=wars),
                                                           VASSAL_METRICS)) if rec else {})
        return subject_cache[sid]

    seen: set[int] = set()
    for cands in wanted:
        cid = next((c for c in cands if record(c)), None)
        if cid is None or cid in seen:
            continue
        seen.add(cid)
        tag = tags.get(str(cid))
        direct = _subjects(children, cid, all_levels=False)
        every = _subjects(children, cid, all_levels=True)
        ctx = Context(country_id=cid, subunits=subunits, wars=wars, vassals=direct, all_vassals=every)
        metrics = with_rebels(cid, compute(record(cid), ctx))
        for scope, vassals in (("direct", direct), ("all", every)):
            for name in VASSAL_METRICS:
                metrics[vassal_metric(name, scope)] = metrics[name] + sum(
                    subject_metrics(s).get(name, 0.0) for s in vassals)
        stats.countries.append(CountryStats(cid, tag, players.get(cid, []), metrics))
    return stats
