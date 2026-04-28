from __future__ import annotations

import re
from typing import List


def normalize_size_tokens(tokens: List[str], option_kind: str = "") -> List[str]:
    out: list[str] = []
    seen = set()
    for token in tokens:
        value = re.sub(r"\s+", " ", (token or "").strip())
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out

