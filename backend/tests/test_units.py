"""Fast unit tests on synthetic token streams (no save files needed)."""
import struct

import pytest

from app.eu5 import lexer as L
from app.eu5.parser import index_top_level, parse, skip_value
from app.eu5.string_lookup import parse_string_lookup
from app.eu5.tokens import TokenTable
from app.eu5.values import format_date

STRINGS = ["a", "b", "c", "rgb_like"]


def tok(t: int) -> bytes:
    return struct.pack("<H", t)


EQ, OP, CL = tok(L.EQUAL), tok(L.OPEN), tok(L.CLOSE)


def key(idx: int) -> bytes:  # u8 lookup
    return tok(0x0D5A) + bytes([idx])


def i32(v: int) -> bytes:
    return tok(L.I32) + struct.pack("<i", v)


def run(buf: bytes, **kw):
    return parse(buf, STRINGS, TokenTable(), **kw)


def test_format_date():
    assert format_date(0x03530F28) == "1367.1.5"
    base = (5000 + 1444) * 365 * 24
    assert format_date(base) == "1444.1.1"
    assert format_date(base + 31 * 24) == "1444.2.1"
    assert format_date(base + 364 * 24) == "1444.12.31"
    assert format_date(base + 5) == "1444.1.1.5"


def test_string_lookup_roundtrip():
    words = ["current_age", "speed", "ñandú"]
    body = b"".join(struct.pack("<H", len(w.encode())) + w.encode() for w in words)
    data = b"\x01" + struct.pack("<H", len(words)) + b"\x00\x00" + body
    assert parse_string_lookup(data) == words
    with pytest.raises(ValueError):
        parse_string_lookup(b"\x01" + struct.pack("<H", 99) + b"\x00\x00" + body)


def test_scalar_types():
    buf = (
        key(0) + EQ + i32(-7)
        + key(1) + EQ + tok(0x0D4A) + (100000).to_bytes(3, "little")  # fixed5 +1.0
        + key(2) + EQ + tok(0x0D51) + (150000).to_bytes(3, "little")  # fixed5 -1.5
        + tok(0x0D3E) + struct.pack("<H", 3) + EQ + tok(L.FIXED5_ZERO)  # u16 lookup key
    )
    assert run(buf) == {"a": -7, "b": 1.0, "c": -1.5, "rgb_like": 0.0}


def test_empty_string_token():
    """0x0d42 has no payload: the next token is the following key (seen as `subunit_name_2`)."""
    buf = tok(L.OPEN) + key(0) + EQ + tok(L.EMPTY_STRING) + key(1) + EQ + i32(3) + tok(L.CLOSE)
    buf = key(2) + EQ + buf
    assert run(buf) == {"c": {"a": "", "b": 3}}
    assert skip_value(buf, 5) == len(buf)  # value starts after the u8 key (3 bytes) and `=`
    assert [t for _, t, _ in L.iter_tokens(buf)].count(L.EMPTY_STRING) == 1
    assert run(buf, select={"c": {"b": True}}) == {"c": {"b": 3}}


def test_blocks_and_repeats():
    buf = (
        key(0) + EQ + OP + i32(1) + i32(2) + CL          # a = { 1 2 }
        + key(1) + EQ + OP + CL                          # b = { }
        + key(2) + EQ + i32(1) + key(2) + EQ + i32(2)    # c = 1  c = 2
    )
    assert run(buf) == {"a": [1, 2], "b": [], "c": [1, 2]}


def test_mixed_block_and_block_key():
    buf = (
        key(0) + EQ + OP + i32(1) + key(1) + EQ + i32(2) + CL   # a = { 1 b = 2 }
        + OP + key(2) + EQ + i32(3) + CL + EQ + i32(4)          # { c = 3 } = 4
    )
    assert run(buf) == {"a": [1, {"b": 2}], '{"c":3}': 4}


def test_tagged_block_and_native_tokens():
    buf = (
        tok(0x09DE) + EQ + tok(0x1234) + OP + i32(1) + CL  # 0x09de = 0x1234 { 1 }
        + key(0) + EQ + tok(0x0222)                        # a = 0x0222
    )
    tokens = TokenTable({0x1234: "rgb"})
    assert parse(buf, STRINGS, tokens) == {"0x09de": {"rgb": [1]}, "a": "0x0222"}


def test_tagged_block_with_lookup_string():
    # color = rgb { 1 2 3 } where "rgb" comes from string_lookup (as in EU5 country records)
    buf = key(0) + EQ + key(3) + OP + i32(1) + i32(2) + i32(3) + CL + key(1) + EQ + i32(5)
    assert run(buf) == {"a": {"rgb_like": [1, 2, 3]}, "b": 5}


# --- selective parsing --------------------------------------------------------------

NESTED = (
    key(0) + EQ + OP + key(1) + EQ + OP + i32(1) + i32(2) + CL + key(2) + EQ + i32(3) + CL  # a={b={1 2} c=3}
    + key(1) + EQ + key(3) + OP + i32(9) + CL                                               # b=rgb_like{9}
    + key(2) + EQ + tok(L.QUOTED) + struct.pack("<H", 2) + b"hi"                           # c="hi"
    + key(2) + EQ + i32(4)                                                                 # c=4
)


def test_skip_value():
    # scalar
    assert skip_value(i32(7) + i32(8), 0) == 6
    # string
    s = tok(L.QUOTED) + struct.pack("<H", 3) + b"abc"
    assert skip_value(s + i32(1), 0) == len(s)
    # nested block
    blk = OP + i32(1) + OP + i32(2) + CL + CL
    assert skip_value(blk + i32(1), 0) == len(blk)
    # tag { ... }
    tagged = key(3) + OP + i32(1) + CL
    assert skip_value(tagged + i32(1), 0) == len(tagged)
    # numeric followed by a block is NOT a tag
    assert skip_value(i32(1) + OP + CL, 0) == 6
    with pytest.raises(L.TokenError):
        skip_value(tok(0x0D5F) + b"\x00", 0)


def test_select():
    assert run(NESTED, select={"a": {"c": True}}) == {"a": {"c": 3}}
    assert run(NESTED, select={"a": True, "c": True}) == {"a": {"b": [1, 2], "c": 3}, "c": ["hi", 4]}
    assert run(NESTED, select={"b": True}) == {"b": {"rgb_like": [9]}}
    assert run(NESTED, select={"zzz": True}) == {}
    assert run(NESTED, select=None) == run(NESTED)


def test_index_top_level():
    idx = index_top_level(NESTED, STRINGS, TokenTable())
    assert set(idx) == {"a", "b", "c"}
    assert len(idx["c"]) == 2
    # Each range parses on its own to exactly that entry.
    mv = memoryview(NESTED)
    (s, e), = idx["a"]
    assert run(mv[s:e]) == {"a": {"b": [1, 2], "c": 3}}
    assert [run(mv[s:e]) for s, e in idx["c"]] == [{"c": "hi"}, {"c": 4}]
    # Ranges are contiguous and cover the whole buffer.
    ranges = sorted(r for rs in idx.values() for r in rs)
    assert ranges[0][0] == 0 and ranges[-1][1] == len(NESTED)
    assert all(a[1] == b[0] for a, b in zip(ranges, ranges[1:]))


def test_dates_option():
    date = 0x03530F28
    buf = key(0) + EQ + i32(date)
    assert run(buf) == {"a": "1367.1.5"}
    assert run(buf, dates=False) == {"a": date}


def test_strict_rejects_unknown_type_token():
    buf = key(0) + EQ + OP + key(1) + EQ + tok(0x0D5F) + b"\x00\x00"
    with pytest.raises(L.TokenError):
        run(buf)
    errors: list = []
    assert run(buf, strict=False, errors=errors) == {"a": []}
    assert errors and "0x0d5f" in errors[0]


def test_unbalanced():
    with pytest.raises(L.TokenError):
        run(key(0) + EQ + OP + i32(1))
    with pytest.raises(L.TokenError):
        run(i32(1) + CL)
