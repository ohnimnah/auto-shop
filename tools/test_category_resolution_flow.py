"""Test StandardCategory correction layer with fallback counts.

Does not upload. Standalone classification report only.
"""

from __future__ import annotations

import os
import sys
from typing import Dict, List

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from marketplace.buyma.category import build_buyma_category_plan


def _identity_corrector(base_category: str, product_name: str, musinsa_category: str) -> str:
    return base_category or ""


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        b = (text or "").encode(enc, errors="replace")
        print(b.decode(enc, errors="replace"))


def _samples() -> List[Dict[str, str]]:
    return [
        {"product_name_kr": "오버핏 후드티", "musinsa_category_large": "남성", "musinsa_category_middle": "상의", "musinsa_category_small": "후드티"},
        {"product_name_kr": "기모 맨투맨", "musinsa_category_large": "여성", "musinsa_category_middle": "상의", "musinsa_category_small": "스웨트셔츠"},
        {"product_name_kr": "베이직 반팔 티셔츠", "musinsa_category_large": "남성", "musinsa_category_middle": "상의", "musinsa_category_small": "티셔츠"},
        {"product_name_kr": "셔츠 블라우스", "musinsa_category_large": "여성", "musinsa_category_middle": "상의", "musinsa_category_small": "셔츠"},
        {"product_name_kr": "울 니트 스웨터", "musinsa_category_large": "남성", "musinsa_category_middle": "상의", "musinsa_category_small": "니트"},
        {"product_name_kr": "브이넥 가디건", "musinsa_category_large": "여성", "musinsa_category_middle": "상의", "musinsa_category_small": "가디건"},
        {"product_name_kr": "코튼 파자마 세트", "musinsa_category_large": "여성", "musinsa_category_middle": "이너웨어", "musinsa_category_small": "잠옷"},
        {"product_name_kr": "다운 패딩 재킷", "musinsa_category_large": "남성", "musinsa_category_middle": "아우터", "musinsa_category_small": "패딩"},
        {"product_name_kr": "테이퍼드 팬츠", "musinsa_category_large": "남성", "musinsa_category_middle": "바지", "musinsa_category_small": "팬츠"},
        {"product_name_kr": "데님 청바지", "musinsa_category_large": "여성", "musinsa_category_middle": "바지", "musinsa_category_small": "데님"},
        {"product_name_kr": "러닝 스니커즈", "musinsa_category_large": "남성", "musinsa_category_middle": "신발", "musinsa_category_small": "스니커즈"},
        {"product_name_kr": "실크 원피스", "musinsa_category_large": "여성", "musinsa_category_middle": "원피스", "musinsa_category_small": "원피스"},
    ]


def main() -> int:
    samples = _samples()
    mapped_by_new = 0
    used_fallback = 0
    still_etc = 0
    misclassified: List[str] = []

    _safe_print("=== Category Resolution Test ===")
    for i, row in enumerate(samples, start=1):
        plan = build_buyma_category_plan(row, category_corrector=_identity_corrector)
        std = plan.get("standard_category", "")
        new_used = bool(plan.get("mapping_table_used"))
        fallback_used = bool(plan.get("semantic_fallback_used"))
        cat1, cat2, cat3 = plan.get("cat1", ""), plan.get("cat2", ""), plan.get("cat3", "")

        if new_used:
            mapped_by_new += 1
        if fallback_used:
            used_fallback += 1
        if std == "ETC":
            still_etc += 1
            misclassified.append(f"{row.get('product_name_kr','')}: standard=ETC")

        _safe_print(f"{i:02d}. {row.get('product_name_kr','')} | std={std} | new={new_used} | fallback={fallback_used} | buyma={cat1} > {cat2} > {cat3}")

    _safe_print("\n=== Summary ===")
    _safe_print(f"total: {len(samples)}")
    _safe_print(f"mapped by new logic: {mapped_by_new}")
    _safe_print(f"used fallback: {used_fallback}")
    _safe_print(f"still ETC: {still_etc}")
    if misclassified:
        _safe_print("obvious misclassification cases:")
        for x in misclassified:
            _safe_print(f"- {x}")
    else:
        _safe_print("obvious misclassification cases: none in this sample set")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
