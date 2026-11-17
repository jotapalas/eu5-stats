"""Binary token stream -> JSON-compatible tree.

Block conversion rules:
  * only `key=value` entries -> dict (a repeated key becomes a list of its values)
  * only bare values         -> list
  * empty block              -> []
  * mixed                    -> list where `key=value` entries become {key: value}
  * `key = tag { ... }` (e.g. `color = rgb { 1 2 3 }`) -> key: {tag: block}

Selective parsing:
  * `parse(..., select=...)` builds only the selected keys and skips the rest without
    building objects. `select` is a tree of nested dicts: {key: True | {subkey: ...}}.
    `True` keeps the whole subtree; unlisted keys and bare values are dropped.
  * `index_top_level()` finds the byte range of every top-level `key = value`, so a
    single section can be parsed later from a memoryview slice.
"""
from __future__ import annotations

from collections import Counter

import orjson

from . import lexer as L
from .string_lookup import decode_text
from .tokens import TokenTable
from .values import FIXED5_SCALE, format_date, looks_like_date

PLAIN, INT32, NAME = 0, 1, 2

Selector = dict  # {key: True | Selector}


# --------------------------------------------------------------------------- skipping

def _build_size_table() -> list[int]:
    """Payload size per token: >0 fixed bytes, -1 length-prefixed string, 0 none."""
    size = [0] * 65536
    for t, s in {L.I32: 4, L.U32: 4, L.F32: 4, L.BOOL: 1, L.F64: 8, L.U64: 8, L.I64: 8}.items():
        size[t] = s
    for t in L.LOOKUP_U8:
        size[t] = 1
    for t in L.LOOKUP_U16:
        size[t] = 2
    for t, s in L.FIXED5_POS.items():
        size[t] = s
    for t, s in L.FIXED5_NEG.items():
        size[t] = s
    size[L.QUOTED] = size[L.UNQUOTED] = -1
    for t in L.EU5_TYPE_RANGE:
        if t not in L.KNOWN:
            size[t] = -2  # unknown value type: cannot be skipped safely
    return size


_SIZE = _build_size_table()
# Tokens that can act as the tag in `key = tag { ... }`: strings and native name tokens.
_NUMERIC = frozenset(
    {L.I32, L.U32, L.F32, L.BOOL, L.F64, L.U64, L.I64, L.FIXED5_ZERO}
    | set(L.FIXED5_POS) | set(L.FIXED5_NEG)
)


def skip_block(buf, i: int) -> int:
    """Skip to just past the `}` matching an already consumed `{` at offset i-2."""
    size = _SIZE
    n = len(buf)
    depth = 1
    while i < n:
        t = buf[i] | (buf[i + 1] << 8)
        i += 2
        s = size[t]
        if s > 0:
            i += s
        elif s == -1:
            i += 2 + (buf[i] | (buf[i + 1] << 8))
        elif t == 3:
            depth += 1
        elif t == 4:
            depth -= 1
            if depth == 0:
                return i
        elif s == -2:
            raise L.TokenError(f"Unknown EU5 value token {t:#06x}", buf, i - 2)
    raise L.TokenError("Unbalanced '{' while skipping", buf, n)


def skip_value(buf, i: int) -> int:
    """Skip the value starting at offset i (after `key =`). Returns the offset after it."""
    n = len(buf)
    t = buf[i] | (buf[i + 1] << 8)
    i += 2
    if t == L.OPEN:
        return skip_block(buf, i)
    s = _SIZE[t]
    if s > 0:
        i += s
    elif s == -1:
        i += 2 + (buf[i] | (buf[i + 1] << 8))
    elif s == -2:
        raise L.TokenError(f"Unknown EU5 value token {t:#06x}", buf, i - 2)
    elif t in (L.EQUAL, L.CLOSE):
        raise L.TokenError(f"Expected a value, got {t:#06x}", buf, i - 2)
    if t not in _NUMERIC and i + 2 <= n and buf[i] == L.OPEN and buf[i + 1] == 0:
        return skip_block(buf, i + 2)  # `tag { ... }`
    return i


def index_top_level(buf, strings: list[str], tokens: TokenTable) -> dict[str, list[tuple[int, int]]]:
    """Map each top-level key to the (start, end) byte ranges of its `key = value` entries.

    A range can be parsed on its own: parse(memoryview(buf)[start:end], ...) -> {key: value}.
    Top-level bare values and block keys are skipped.
    """
    out: dict[str, list[tuple[int, int]]] = {}
    n = len(buf)
    i = 0
    while i < n:
        start = i
        t = buf[i] | (buf[i + 1] << 8)
        if t == L.OPEN:
            i = skip_block(buf, i + 2)
            if i + 2 <= n and buf[i] == L.EQUAL and buf[i + 1] == 0:
                i = skip_value(buf, i + 2)
            continue
        if t in (L.CLOSE, L.EQUAL):
            raise L.TokenError(f"Unexpected {t:#06x} at top level", buf, i)
        i += 2
        s = _SIZE[t]
        if t in L.LOOKUP_U8:
            key = strings[buf[i]]
        elif t in L.LOOKUP_U16:
            key = strings[buf[i] | (buf[i + 1] << 8)]
        elif s == -1:
            ln = buf[i] | (buf[i + 1] << 8)
            key = decode_text(bytes(buf[i + 2 : i + 2 + ln]))
        elif s == -2:
            raise L.TokenError(f"Unknown EU5 value token {t:#06x}", buf, i - 2)
        elif t == L.EMPTY_STRING:
            key = ""
        elif s == 0 and t not in _NUMERIC:
            key = tokens.resolve(t)
        else:
            key = None  # numeric key; rare at top level, not indexed by name
        i += s if s > 0 else (2 + (buf[i] | (buf[i + 1] << 8)) if s == -1 else 0)
        if i + 2 <= n and buf[i] == L.EQUAL and buf[i + 1] == 0:
            i = skip_value(buf, i + 2)
            if key is not None:
                out.setdefault(key, []).append((start, i))
    return out


# --------------------------------------------------------------------------- parsing

class _Frame:
    __slots__ = ("items", "has_kv", "has_bare", "key", "tag", "sel")

    def __init__(self, key, tag=None, sel=None):
        self.items: list = []
        self.has_kv = False
        self.has_bare = False
        self.key = key  # key in parent, or None for a bare block
        self.tag = tag  # e.g. "rgb" for `color = rgb { ... }`
        self.sel = sel  # None = keep everything, dict = keep only these keys

    def add(self, key, value):
        if key is None:
            self.has_bare = True
        else:
            self.has_kv = True
        self.items.append((key, value))

    def finish(self):
        items = self.items
        if not items:
            out = {} if self.sel is not None else []
        elif not self.has_bare:
            out = {}
            repeated = set()
            for k, v in items:
                if k in out:
                    if k in repeated:
                        out[k].append(v)
                    else:
                        out[k] = [out[k], v]
                        repeated.add(k)
                else:
                    out[k] = v
        elif not self.has_kv:
            out = [v for _, v in items]
        else:
            out = [v if k is None else {k: v} for k, v in items]
        return {self.tag: out} if self.tag is not None else out


def _key_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _child_selector(sel: Selector, key: str):
    """-> (keep, child_sel). child_sel None means keep the whole subtree."""
    sub = sel.get(key)
    if sub is None or sub is False:
        return False, None
    return True, (None if sub is True else sub)


def parse(
    buf,
    strings: list[str],
    tokens: TokenTable,
    *,
    dates: bool = True,
    strict: bool = True,
    unknown: Counter | None = None,
    errors: list | None = None,
    select: Selector | None = None,
):
    """Parse a binary stream (bytes or memoryview slice) into a dict/list."""
    u16, i32, u32, f32, i64, u64 = L.u16, L.i32, L.u32, L.f32, L.i64, L.u64
    from_bytes = int.from_bytes
    LOOKUP_U8, LOOKUP_U16 = L.LOOKUP_U8, L.LOOKUP_U16
    FPOS, FNEG = L.FIXED5_POS, L.FIXED5_NEG
    EQUAL, OPEN, CLOSE = L.EQUAL, L.OPEN, L.CLOSE
    n = len(buf)

    def scalar(t, i):
        """Read one scalar starting after token t at offset i -> (value, next_i, kind)."""
        if t in LOOKUP_U16:
            return strings[u16(buf, i)[0]], i + 2, PLAIN
        if t in FPOS:
            size = FPOS[t]
            return from_bytes(buf[i : i + size], "little") / FIXED5_SCALE, i + size, PLAIN
        if t in LOOKUP_U8:
            return strings[buf[i]], i + 1, PLAIN
        if t == L.I32:
            return i32(buf, i)[0], i + 4, INT32
        if t == L.FIXED5_ZERO:
            return 0.0, i, PLAIN
        if t == L.EMPTY_STRING:
            return "", i, PLAIN
        if t in FNEG:
            size = FNEG[t]
            return -from_bytes(buf[i : i + size], "little") / FIXED5_SCALE, i + size, PLAIN
        if t == L.U32:
            return u32(buf, i)[0], i + 4, PLAIN
        if t == L.QUOTED or t == L.UNQUOTED:
            ln = u16(buf, i)[0]
            return decode_text(bytes(buf[i + 2 : i + 2 + ln])), i + 2 + ln, PLAIN
        if t == L.BOOL:
            return buf[i] != 0, i + 1, PLAIN
        if t == L.F64:
            return i64(buf, i)[0] / FIXED5_SCALE, i + 8, PLAIN
        if t == L.U64:
            return u64(buf, i)[0], i + 8, PLAIN
        if t == L.I64:
            return i64(buf, i)[0], i + 8, PLAIN
        if t == L.F32:
            return f32(buf, i)[0], i + 4, PLAIN
        if L.is_unknown_type(t):
            raise L.TokenError(f"Unknown EU5 value token {t:#06x}", buf, i - 2)
        return tokens.resolve(t, unknown), i, NAME

    root = _Frame(None, sel=select)
    stack = [root]

    def read_value(key, i, child_sel):
        """Read the value after `key =`; either stores it or opens a block. Returns next offset."""
        t = u16(buf, i)[0]
        i += 2
        if t == OPEN:
            stack.append(_Frame(key, sel=child_sel))
            return i
        value, i, kind = scalar(t, i)
        if (kind == NAME or isinstance(value, str)) and i + 2 <= n and u16(buf, i)[0] == OPEN:
            # `key = tag { ... }` (tag may be a native token or a string, e.g. rgb)
            stack.append(_Frame(key, tag=value, sel=child_sel))
            return i + 2
        if kind == INT32 and dates and looks_like_date(key, value):
            value = format_date(value)
        stack[-1].add(key, value)
        return i

    i = 0
    try:
        while i < n:
            t = u16(buf, i)[0]
            i += 2
            if t == CLOSE:
                if len(stack) == 1:
                    raise L.TokenError("Unbalanced '}'", buf, i - 2)
                done = stack.pop()
                block = done.finish()
                if done.key is None and i + 2 <= n and u16(buf, i)[0] == EQUAL:
                    # `{ ... } = value`: a block used as a key -> compact JSON text key
                    i = read_value(orjson.dumps(block).decode(), i + 2, None)
                else:
                    stack[-1].add(done.key, block)
                continue
            if t == OPEN:
                if stack[-1].sel is not None:
                    # Bare block inside a filtered block: not selectable, skip it
                    # (and its value, if it is a block key).
                    i = skip_block(buf, i)
                    if i + 2 <= n and u16(buf, i)[0] == EQUAL:
                        i = skip_value(buf, i + 2)
                    continue
                stack.append(_Frame(None))
                continue
            if t == EQUAL:
                raise L.TokenError("Unexpected '='", buf, i - 2)

            value, i, kind = scalar(t, i)
            if i + 2 <= n and u16(buf, i)[0] == EQUAL:
                key = _key_text(value)
                sel = stack[-1].sel
                if sel is None:
                    i = read_value(key, i + 2, None)
                else:
                    keep, child_sel = _child_selector(sel, key)
                    i = read_value(key, i + 2, child_sel) if keep else skip_value(buf, i + 2)
            elif stack[-1].sel is None:
                stack[-1].add(None, value)
    except (L.TokenError, IndexError) as e:
        if strict:
            raise
        if errors is not None:
            errors.append(str(e))
        # Close any open blocks so the partial result is still well-formed.
        while len(stack) > 1:
            done = stack.pop()
            stack[-1].add(done.key, done.finish())
    else:
        if len(stack) != 1:
            msg = f"Unbalanced '{{': {len(stack) - 1} block(s) left open"
            if strict:
                raise L.TokenError(msg, buf, n)
            if errors is not None:
                errors.append(msg)
            while len(stack) > 1:
                done = stack.pop()
                stack[-1].add(done.key, done.finish())
    return root.finish()
