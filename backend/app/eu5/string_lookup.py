"""Parser for the `string_lookup` ZIP entry.

Layout (inferred from real saves):
    u8   version (observed: 1)
    u16  entry count (low 16 bits)
    u16  unknown
    then `count` entries of: u16 length + bytes (UTF-8)
"""
from __future__ import annotations

import struct

HEADER_LEN = 5


def decode_text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def parse_string_lookup(data: bytes | None) -> list[str]:
    if not data:
        return []
    count = struct.unpack_from("<H", data, 1)[0]
    out: list[str] = []
    i, n = HEADER_LEN, len(data)
    unpack = struct.Struct("<H").unpack_from
    while i + 2 <= n:
        length = unpack(data, i)[0]
        i += 2
        out.append(decode_text(data[i : i + length]))
        i += length
    if i != n or (len(out) & 0xFFFF) != count:
        raise ValueError(
            f"string_lookup mismatch: parsed {len(out)} entries ending at {i}/{n}, header count {count}"
        )
    return out
