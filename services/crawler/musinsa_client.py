from __future__ import annotations

import json
import urllib.request
from typing import Dict


def fetch_json(url: str) -> Dict[str, object]:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)

