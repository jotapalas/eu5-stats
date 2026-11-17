"""Token definitions for the EU5 binary (Clausewitz/Jomini) format.

Every token is a little-endian u16. Control and value-type tokens are listed here;
any other u16 is a native "name" token whose text lives in the game executable
(resolved, if known, via tokens/eu5.txt).

EU5-specific tokens (0x0d3e-0x0d5b) were identified empirically from real saves:
  * lookups: index into the `string_lookup` table (u8 or u16 little-endian)
  * fixed5:  unsigned magnitude of 0..7 bytes, value = +-raw / 100000
"""
from __future__ import annotations

import struct
from typing import Iterator

EQUAL = 0x0001
OPEN = 0x0003
CLOSE = 0x0004

I32 = 0x000C
F32 = 0x000D  # not observed in EU5 saves yet; decoded as IEEE float
BOOL = 0x000E
QUOTED = 0x000F
U32 = 0x0014
UNQUOTED = 0x0017
F64 = 0x0167  # i64 fixed-point / 100000
U64 = 0x029C
I64 = 0x0317  # not observed in EU5 saves yet

LOOKUP_U8 = frozenset({0x0D40, 0x0D43, 0x0D5A})
LOOKUP_U16 = frozenset({0x0D3E, 0x0D44, 0x0D5B})

FIXED5_ZERO = 0x0D47
FIXED5_POS = {0x0D48 + k: k + 1 for k in range(7)}  # 0x0d48..0x0d4e -> 1..7 bytes
FIXED5_NEG = {0x0D4F + k: k + 1 for k in range(7)}  # 0x0d4f..0x0d55 -> 1..7 bytes

# Range where EU5 defines its own value types. Unknown tokens here are almost
# certainly a new value type with a payload, so we refuse to guess.
EU5_TYPE_RANGE = range(0x0D3E, 0x0D60)

KNOWN = (
    {EQUAL, OPEN, CLOSE, I32, F32, BOOL, QUOTED, U32, UNQUOTED, F64, U64, I64, FIXED5_ZERO}
    | LOOKUP_U8
    | LOOKUP_U16
    | set(FIXED5_POS)
    | set(FIXED5_NEG)
)

u16 = struct.Struct("<H").unpack_from
i32 = struct.Struct("<i").unpack_from
u32 = struct.Struct("<I").unpack_from
f32 = struct.Struct("<f").unpack_from
i64 = struct.Struct("<q").unpack_from
u64 = struct.Struct("<Q").unpack_from


class TokenError(ValueError):
    def __init__(self, msg: str, buf: bytes, offset: int):
        ctx = bytes(buf[max(0, offset - 16) : offset + 32]).hex(" ", 2)
        super().__init__(f"{msg} at offset {offset} (context: {ctx})")
        self.offset = offset


def is_unknown_type(token: int) -> bool:
    return token in EU5_TYPE_RANGE and token not in KNOWN


def iter_tokens(buf: bytes) -> Iterator[tuple[int, int, object]]:
    """Yield (offset, token, payload). Simple and slow; used by tools and tests.

    payload: raw python value for value tokens, lookup index for lookups,
    signed raw integer for fixed5, None for control/name tokens.
    """
    i, n = 0, len(buf)
    while i < n:
        off = i
        t = u16(buf, i)[0]
        i += 2
        if t == I32:
            v = i32(buf, i)[0]; i += 4
        elif t == U32:
            v = u32(buf, i)[0]; i += 4
        elif t == F32:
            v = f32(buf, i)[0]; i += 4
        elif t == BOOL:
            v = buf[i] != 0; i += 1
        elif t == QUOTED or t == UNQUOTED:
            ln = u16(buf, i)[0]
            v = bytes(buf[i + 2 : i + 2 + ln]); i += 2 + ln
        elif t == F64:
            v = i64(buf, i)[0]; i += 8
        elif t == U64:
            v = u64(buf, i)[0]; i += 8
        elif t == I64:
            v = i64(buf, i)[0]; i += 8
        elif t in LOOKUP_U8:
            v = buf[i]; i += 1
        elif t in LOOKUP_U16:
            v = u16(buf, i)[0]; i += 2
        elif t == FIXED5_ZERO:
            v = 0
        elif t in FIXED5_POS:
            size = FIXED5_POS[t]
            v = int.from_bytes(buf[i : i + size], "little"); i += size
        elif t in FIXED5_NEG:
            size = FIXED5_NEG[t]
            v = -int.from_bytes(buf[i : i + size], "little"); i += size
        elif is_unknown_type(t):
            raise TokenError(f"Unknown EU5 value token {t:#06x}", buf, off)
        else:
            v = None
        if i > n:
            raise TokenError("Truncated token payload", buf, off)
        yield off, t, v
