"""EU5 save container: 32-byte ASCII header + binary metadata + ZIP (gamestate, string_lookup)."""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

HEADER_LEN = 32


class SaveFormatError(ValueError):
    pass


@dataclass
class Header:
    version: int
    save_type: int
    unknown: str
    metadata_len: int
    trailer: str

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "save_type": self.save_type,
            "unknown": self.unknown,
            "metadata_len": self.metadata_len,
            "trailer": self.trailer,
        }


@dataclass
class SaveContainer:
    header: Header
    metadata: bytes
    gamestate: bytes | None
    string_lookup: bytes | None


def parse_header(data: bytes) -> Header:
    if len(data) < HEADER_LEN or data[:3] != b"SAV":
        raise SaveFormatError("Not an EU5 save: missing 'SAV' magic")
    raw = data[:HEADER_LEN]
    if raw[-1:] != b"\n":
        raise SaveFormatError(f"Malformed header: {raw!r}")
    text = raw[3:-1].decode("ascii")  # 28 chars: VV TT XXXXXXXX LLLLLLLL ZZZZZZZZ
    try:
        return Header(
            version=int(text[0:2], 16),
            save_type=int(text[2:4], 16),
            unknown=text[4:12],
            metadata_len=int(text[12:20], 16),
            trailer=text[20:28],
        )
    except ValueError as e:
        raise SaveFormatError(f"Malformed header: {raw!r}") from e


def open_save(data: bytes, *, with_gamestate: bool = True) -> SaveContainer:
    header = parse_header(data)
    meta_end = HEADER_LEN + header.metadata_len
    if meta_end > len(data):
        raise SaveFormatError("Metadata length exceeds file size")
    metadata = data[HEADER_LEN:meta_end]

    gamestate = string_lookup = None
    zip_start = data.find(b"PK\x03\x04", meta_end)
    if zip_start < 0:
        raise SaveFormatError("ZIP section not found")
    zf = zipfile.ZipFile(io.BytesIO(memoryview(data)[zip_start:]))
    names = set(zf.namelist())
    if "string_lookup" in names:
        string_lookup = zf.read("string_lookup")
    if with_gamestate:
        if "gamestate" not in names:
            raise SaveFormatError(f"ZIP has no 'gamestate' entry: {sorted(names)}")
        gamestate = zf.read("gamestate")
    return SaveContainer(header, metadata, gamestate, string_lookup)
