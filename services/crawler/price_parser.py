from __future__ import annotations

import re
from bs4 import BeautifulSoup


def extract_discounted_product_price(soup: BeautifulSoup | None) -> str:
    if soup is None:
        return "가격 미확인"
    text = soup.get_text(" ", strip=True)
    prices = [int(v.replace(",", "")) for v in re.findall(r"\d{1,3}(?:,\d{3})+|\d{4,}", text)]
    if not prices:
        return "가격 미확인"
    return f"{min(prices):,}"

