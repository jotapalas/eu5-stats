"""Native token name table (id -> name), loaded from an optional text file.

Format, one per line:  `0x09de current_age`  (hex or decimal id). `#` starts a comment.
Unresolved ids are rendered as "0xNNNN".
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "tokens" / "eu5.txt"


class TokenTable:
    def __init__(self, names: dict[int, str] | None = None):
        self.names = names or {}

    @classmethod
    def load(cls, path: Path | str = DEFAULT_PATH) -> "TokenTable":
        names: dict[int, str] = {}
        p = Path(path)
        if p.exists():
            for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                line = line.split("#", 1)[0].strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) != 2:
                    raise ValueError(f"{p}:{lineno}: expected '<id> <name>', got {line!r}")
                names[int(parts[0], 0)] = parts[1]
        return cls(names)

    def resolve(self, token: int, unknown: Counter | None = None) -> str:
        name = self.names.get(token)
        if name is None:
            name = f"0x{token:04x}"
            if unknown is not None:
                unknown[name] += 1
        return name
