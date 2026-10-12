from __future__ import annotations

import re

_PARTS = re.compile(r"(\d+)")


def natural_key(value: str) -> tuple[object, ...]:
    return tuple(int(part) if part.isdigit() else part.casefold() for part in _PARTS.split(value))
