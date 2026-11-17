"""High-level entry point: raw .eu5 bytes -> JSON-compatible dict."""
from __future__ import annotations

from collections import Counter

from .container import open_save
from .parser import parse
from .string_lookup import parse_string_lookup
from .tokens import TokenTable

SECTIONS = ("header", "metadata", "gamestate")


def decode_save(
    data: bytes,
    *,
    sections: tuple[str, ...] = SECTIONS,
    tokens: TokenTable | None = None,
    dates: bool = True,
    strict: bool = True,
    select: tuple[str, ...] | None = None,
) -> dict:
    """Decode a save. `select` limits the gamestate to these top-level keys (others are skipped)."""
    bad = set(sections) - set(SECTIONS)
    if bad:
        raise ValueError(f"Unknown sections: {sorted(bad)}")
    tokens = tokens or TokenTable.load()
    container = open_save(data, with_gamestate="gamestate" in sections)
    strings = parse_string_lookup(container.string_lookup)
    unknown: Counter = Counter()
    errors: list[str] = []
    opts = dict(dates=dates, strict=strict, unknown=unknown, errors=errors)

    out: dict = {}
    if "header" in sections:
        out["header"] = container.header.to_dict()
    if "metadata" in sections:
        out["metadata"] = parse(container.metadata, strings, tokens, **opts)
    if "gamestate" in sections:
        gs_select = {k: True for k in select} if select else None
        out["gamestate"] = parse(container.gamestate, strings, tokens, select=gs_select, **opts)
    out["unknown_tokens"] = dict(unknown.most_common())
    if errors:
        out["errors"] = errors
    return out
