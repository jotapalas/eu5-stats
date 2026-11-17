"""Catalogue of per-country metrics extracted from a country record.

Each metric is a function of (country, ctx) -> float. Paradox omits fields whose value
is zero/false, so every lookup defaults to 0.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


def get(d, path: str, default: float = 0.0):
    """Nested lookup: get(country, "score.score_rating.ADM")."""
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def num(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def as_list(v) -> list:
    """Paradox stores a single-element list as a bare value; normalise to a list."""
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def count(value) -> float:
    """Length of a list/dict field; a single scalar counts as 1, missing as 0."""
    if isinstance(value, (list, dict)):
        return float(len(value))
    return 0.0 if value in (None, 0, "") else 1.0


@dataclass
class Context:
    """Data from outside the country record that some metrics need."""
    country_id: int
    subunits: dict = field(default_factory=dict)  # subunit_manager.database
    wars: dict = field(default_factory=dict)  # war_manager.database
    vassals: list[int] = field(default_factory=list)  # direct vassals (see extract._subjects)
    all_vassals: list[int] = field(default_factory=list)  # vassals at every level


@dataclass(frozen=True)
class Metric:
    name: str
    category: str
    description: str
    fn: Callable[[dict, Context], float]


def _subunits(country: dict, ctx: Context, prefix: str) -> list[dict]:
    out = []
    for sid in as_list(country.get("owned_subunits")):
        su = ctx.subunits.get(str(sid))
        if isinstance(su, dict) and str(su.get("type", "")).startswith(prefix):
            out.append(su)
    return out


def _active_wars(country: dict, ctx: Context) -> float:
    n = 0
    for war in ctx.wars.values():
        if not isinstance(war, dict) or "end_date" in war:
            continue
        if any(
            isinstance(p, dict) and p.get("country") == ctx.country_id and p.get("status") == "Active"
            for p in as_list(war.get("all"))
        ):
            n += 1
    return float(n)


def _maintenance(country: dict, ctx: Context) -> float:
    m = country.get("last_month_maintenance")
    return float(sum(num(v) for v in m.values())) if isinstance(m, dict) else 0.0


def _field(path: str) -> Callable[[dict, Context], float]:
    return lambda c, ctx: num(get(c, path))


def _len(path: str) -> Callable[[dict, Context], float]:
    return lambda c, ctx: count(get(c, path, None))


METRICS: list[Metric] = [
    # economy
    Metric("gold", "economy", "Treasury (gold)", _field("currency_data.gold")),
    Metric("monthly_income", "economy", "Gold income last month", _field("last_month_gold_income")),
    Metric("tax_income", "economy", "Tax income last month", _field("last_months_tax_income")),
    Metric("trade_value", "economy", "Monthly trade value", _field("monthly_trade_value")),
    Metric("trade_balance", "economy", "Monthly trade balance", _field("monthly_trade_balance")),
    Metric("inflation", "economy", "Inflation", _field("currency_data.inflation")),
    Metric("maintenance", "economy", "Total maintenance last month", _maintenance),
    Metric("total_produced", "economy", "Total goods produced", _field("total_produced")),
    # size / power
    Metric("population", "size", "Population last month", _field("last_months_population")),
    Metric("locations", "size", "Owned locations", _len("owned_locations")),
    Metric("provinces", "size", "Provinces", _len("provinces")),
    Metric("core_locations", "size", "Core locations", _len("core_locations")),
    Metric("score_place", "size", "Score position (1 = best)", _field("score.score_place")),
    Metric("score_adm", "size", "Administrative score rating", _field("score.score_rating.ADM")),
    Metric("score_dip", "size", "Diplomatic score rating", _field("score.score_rating.DIP")),
    Metric("score_mil", "size", "Military score rating", _field("score.score_rating.MIL")),
    Metric("great_power_rank", "size", "Great power rank", _field("great_power_rank")),
    Metric("vassals", "size", "Direct vassals (subjects except tributaries, Hansa members, secessionists)",
           lambda c, ctx: float(len(ctx.vassals))),
    Metric("all_vassals", "size", "Vassals at every level (vassals of vassals included)",
           lambda c, ctx: float(len(ctx.all_vassals))),
    # military
    Metric("manpower", "military", "Manpower", _field("currency_data.manpower")),
    Metric("max_manpower", "military", "Maximum manpower", _field("max_manpower")),
    Metric("sailors", "military", "Sailors", _field("currency_data.sailors")),
    Metric("max_sailors", "military", "Maximum sailors", _field("max_sailors")),
    Metric("army_tradition", "military", "Army tradition", _field("currency_data.army_tradition")),
    Metric("navy_tradition", "military", "Navy tradition", _field("currency_data.navy_tradition")),
    Metric("army_strength", "military", "Sum of regiment strength",
           lambda c, ctx: float(sum(num(s.get("strength")) for s in _subunits(c, ctx, "a_")))),
    Metric("ships", "military", "Ships (subunits of type n_*)",
           lambda c, ctx: float(len(_subunits(c, ctx, "n_")))),
    Metric("expected_army_size", "military", "Expected army size", _field("expected_army_size")),
    Metric("active_wars", "military", "Wars the country is actively fighting", _active_wars),
    # state / progress
    Metric("stability", "state", "Stability", _field("currency_data.stability")),
    Metric("prestige", "state", "Prestige", _field("currency_data.prestige")),
    Metric("war_exhaustion", "state", "War exhaustion", _field("currency_data.war_exhaustion")),
    Metric("advances", "state", "Researched advances", _len("researched_advances")),
    Metric("institutions", "state", "Embraced institutions", _len("institutions")),
    Metric("political_influence", "state", "Political influence", _field("currency_data.political_influence")),
]

METRICS_BY_NAME = {m.name: m for m in METRICS}

# Subjects (diplomacy_manager.dependency). Excluded types do not add anything (nor does their subtree).
# A `secessionists` entry links a rebel province to the country *backing* it, not to the one it rebels against,
# so it is not the overlord's land.
EXCLUDED_SUBJECTS = frozenset({"tributary", "hanseatic_member", "secessionists"})
VASSAL_METRICS = ("population", "locations", "provinces", "core_locations",
                  "manpower", "max_manpower", "army_strength", "ships")

# During an active civil war the rebels' land still counts for the country they fight (see extract.py).
# core_locations is left alone: the government keeps its cores on rebel-held land, so adding the rebels'
# cores would count them twice.
CIVIL_WAR_METRICS = ("population", "locations", "provinces")

# Aggregated variants (country + vassals) are stored as extra metric names; they are not in METRICS so
# /metrics, the docs and the UI keep listing base metrics only. scope -> suffix.
VASSAL_SCOPES = {"direct": "__vassals", "all": "__all_vassals"}


def vassal_metric(name: str, scope: str) -> str:
    return name + VASSAL_SCOPES[scope]


VASSAL_VARIANTS: dict[str, dict[str, str]] = {
    name: {scope: vassal_metric(name, scope) for scope in VASSAL_SCOPES} for name in VASSAL_METRICS
}
SERIES_METRICS = set(METRICS_BY_NAME) | {v for vs in VASSAL_VARIANTS.values() for v in vs.values()}


def compute(country: dict, ctx: Context, names=None) -> dict[str, float]:
    """All metrics, or only `names`."""
    if names is None:
        return {m.name: m.fn(country, ctx) for m in METRICS}
    return {n: METRICS_BY_NAME[n].fn(country, ctx) for n in names}
