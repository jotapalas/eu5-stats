"""Statistics on unresolved native tokens across saves, to help name them.

For each native token id without a name in tokens/eu5.txt, prints how often it appears,
whether it is used as a key or a value, the value types that follow it, a sample value
and the path where it was first seen.

Usage: python -m tools.token_stats [DIR_OR_FILES...] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from app.eu5 import lexer as L
from app.eu5.container import open_save
from app.eu5.string_lookup import parse_string_lookup
from app.eu5.tokens import TokenTable
from app.eu5.values import format_date, looks_like_date

TYPE_NAMES = {
    L.I32: "i32", L.U32: "u32", L.F32: "f32", L.BOOL: "bool", L.QUOTED: "string",
    L.UNQUOTED: "string", L.F64: "fixed64", L.U64: "u64", L.I64: "i64", L.FIXED5_ZERO: "fixed5",
    **{t: "lookup" for t in L.LOOKUP_U8 | L.LOOKUP_U16},
    **{t: "fixed5" for t in L.FIXED5_POS},
    **{t: "fixed5" for t in L.FIXED5_NEG},
}


def _render(t: int, v, strings: list[str], tokens: TokenTable):
    if t in L.LOOKUP_U8 or t in L.LOOKUP_U16:
        return strings[v]
    if t in L.FIXED5_POS or t in L.FIXED5_NEG or t == L.FIXED5_ZERO or t == L.F64:
        return v / 100_000
    if t in (L.QUOTED, L.UNQUOTED):
        return v.decode("utf-8", "replace")[:80]
    if t in TYPE_NAMES:
        return v
    return tokens.resolve(t)


def collect(paths: list[Path], tokens: TokenTable) -> dict:
    stats: dict = defaultdict(lambda: {"count": 0, "as_key": 0, "as_value": 0,
                                        "value_types": Counter(), "sample": None,
                                        "path": None, "saves": set()})
    for path in paths:
        c = open_save(path.read_bytes())
        strings = parse_string_lookup(c.string_lookup)
        stack: list[str] = []  # path of keys to the current block
        prev = None  # (token, rendered) of the previous scalar, a candidate key
        key = None  # key text when the next token is the value of `key =`
        key_token = None  # unresolved token id used as that key
        for _, t, v in L.iter_tokens(c.gamestate):
            if t == L.EQUAL:
                key = str(prev[1]) if prev else "?"
                key_token = None
                if prev and prev[0] not in TYPE_NAMES and prev[0] not in tokens.names:
                    key_token = prev[0]
                    s = stats[key_token]
                    s["as_key"] += 1
                    s["path"] = s["path"] or "/".join(stack + [key])
                prev = None
                continue
            if t == L.OPEN:
                stack.append(key if key is not None else "[]")
                key, key_token, prev = None, None, None
                continue
            if t == L.CLOSE:
                if stack:
                    stack.pop()
                key, key_token, prev = None, None, None
                continue

            rendered = _render(t, v, strings, tokens)
            unresolved = t not in TYPE_NAMES and t not in tokens.names
            if unresolved:
                s = stats[t]
                s["count"] += 1
                s["saves"].add(path.name)
                if key is not None:
                    s["as_value"] += 1
                    s["path"] = s["path"] or "/".join(stack + [key])
            if key_token is not None:
                s = stats[key_token]
                s["value_types"][TYPE_NAMES.get(t, "token")] += 1
                if s["sample"] is None:
                    if t == L.I32 and looks_like_date(None, v):
                        rendered = f"{v} ({format_date(v)})"
                    s["sample"] = rendered
            key, key_token = None, None
            prev = (t, rendered)
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", default=["."], help="Save files or directories (default: .)")
    ap.add_argument("--json", action="store_true", help="Output JSON")
    args = ap.parse_args(argv)

    files: list[Path] = []
    for p in map(Path, args.paths):
        files.extend(sorted(p.glob("*.eu5")) if p.is_dir() else [p])
    if not files:
        print("No .eu5 files found", file=sys.stderr)
        return 1

    stats = collect(files, TokenTable.load())
    rows = sorted(stats.items())
    if args.json:
        out = {f"0x{t:04x}": {**s, "value_types": dict(s["value_types"]), "saves": len(s["saves"])}
               for t, s in rows}
        print(json.dumps(out, indent=2, default=str, ensure_ascii=False))
        return 0
    print(f"{len(rows)} unresolved token(s) in {len(files)} save(s)\n")
    print(f"{'token':8} {'count':>6} {'key':>5} {'val':>5}  {'types':14} {'sample':30} path")
    for t, s in rows:
        types = ",".join(s["value_types"]) or "-"
        sample = "" if s["sample"] is None else str(s["sample"])[:30]
        print(f"0x{t:04x}  {s['count']:>6} {s['as_key']:>5} {s['as_value']:>5}  {types:14} {sample:30} {s['path'] or ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
