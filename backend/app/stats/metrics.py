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
    units: dict = field(default_factory=dict)  # unit_manager.database
    subunits: dict = field(default_factory=dict)  # subunit_manager.database
    wars: dict = field(default_factory=dict)  # war_manager.database


@dataclass(frozen=True)
class Metric:
    name: str
    category: str
    description: str
    fn: Callable[[dict, Context], float]


def _units(country: dict, ctx: Context, army: bool) -> float:
    n = 0
    for uid in as_list(country.get("units")):
        unit = ctx.units.get(str(uid))
        if isinstance(unit, dict) and bool(unit.get("is_army", False)) == army:
            n += 1
    return float(n)


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
    # military
    Metric("manpower", "military", "Manpower", _field("currency_data.manpower")),
    Metric("max_manpower", "military", "Maximum manpower", _field("max_manpower")),
    Metric("sailors", "military", "Sailors", _field("currency_data.sailors")),
    Metric("max_sailors", "military", "Maximum sailors", _field("max_sailors")),
    Metric("army_tradition", "military", "Army tradition", _field("currency_data.army_tradition")),
    Metric("navy_tradition", "military", "Navy tradition", _field("currency_data.navy_tradition")),
    Metric("armies", "military", "Number of armies", lambda c, ctx: _units(c, ctx, army=True)),
    Metric("navies", "military", "Number of fleets", lambda c, ctx: _units(c, ctx, army=False)),
    Metric("regiments", "military", "Army regiments (subunits of type a_*)",
           lambda c, ctx: float(len(_subunits(c, ctx, "a_")))),
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

# Yearly series kept by the game itself in each country record: field -> metric name.
HISTORY_FIELDS = {
    "historical_population": "population",
    "historical_tax_base": "tax_base",
    "historical_economical_base": "economical_base",
}


def compute(country: dict, ctx: Context) -> dict[str, float]:
    return {m.name: m.fn(country, ctx) for m in METRICS}
