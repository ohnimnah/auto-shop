"""Sheet-driven StandardCategory classifier (minimal additive layer).

Reads keyword rules from Google Sheet and returns StandardCategory when matched.
If unavailable or unmatched, caller should fall back to existing resolver.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import os
import re
from typing import Dict, List, Optional, Tuple

from marketplace.buyma.standard_category import StandardCategory, build_combined_text
from marketplace.common.runtime import get_runtime_data_dir
from marketplace.common import sheet_source as sheet_source_mod


DEFAULT_CLASSIFIER_SHEET = "source_to_standard_mapping"
_CACHE_TTL_SECONDS = 120
_RULE_CACHE: Dict[str, object] = {
    "loaded_at": None,
    "key": "",
    "rules": [],
}


@dataclass
class ClassificationRule:
    standard_category: StandardCategory
    title_keywords_include: List[str]
    priority: int = 100
    enabled: bool = True


def _normalize_text(text: str) -> str:
    value = (text or "").lower().strip()
    for sep in ["/", "\\", "|", ",", ";", "_", "-", "(", ")", "[", "]"]:
        value = value.replace(sep, " ")
    return " ".join(value.split())


def _split_keywords(raw: str) -> List[str]:
    text = (raw or "").strip()
    if not text:
        return []
    parts = re.split(r"[\n,|;/]+", text)
    return [p.strip().lower() for p in parts if p.strip()]


def _parse_bool(value: str, default: bool = True) -> bool:
    text = (value or "").strip().lower()
    if not text:
        return default
    return text in {"1", "y", "yes", "true", "on"}


def _parse_int(value: str, default: int = 100) -> int:
    text = (value or "").strip()
    try:
        return int(text)
    except Exception:
        return default


def _resolve_spreadsheet_id_from_runtime() -> str:
    cfg_path = os.path.join(get_runtime_data_dir(), "sheets_config.json")
    if not os.path.exists(cfg_path):
        return ""
    try:
        with open(cfg_path, "r", encoding="utf-8") as fp:
            cfg = json.load(fp)
        raw_id = str((cfg or {}).get("spreadsheet_id", "") or "")
        return sheet_source_mod.extract_spreadsheet_id(raw_id)
    except Exception:
        return ""


def _to_standard_category(raw: str) -> Optional[StandardCategory]:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return StandardCategory(text)
    except Exception:
        return None


def _load_rules_from_sheet(
    *,
    spreadsheet_id: str,
    sheet_name: str,
    _retried: bool = False,
) -> List[ClassificationRule]:
    if not spreadsheet_id:
        return []

    try:
        credentials_path = sheet_source_mod.get_credentials_path(os.getcwd())
        service = sheet_source_mod.get_sheets_service(credentials_path)
        # 먼저 탭 존재 여부를 확인해 range parse 에러를 피한다.
        meta = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(properties(title))",
        ).execute()
        titles = [
            ((s.get("properties", {}) or {}).get("title") or "").strip()
            for s in meta.get("sheets", [])
        ]
        if sheet_name not in titles:
            print(f"[classifier] sheet not found: '{sheet_name}'")
            print(f"[classifier] available sheets: {titles}")
            return []

        quoted_name = sheet_name.replace("'", "''")
        header_result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{quoted_name}'!A1:ZZ1",
        ).execute()
        header_row = header_result.get("values", [[]])[0] if header_result.get("values") else []
        header_map: Dict[str, int] = {}
        for idx, value in enumerate(header_row):
            key = (value or "").strip()
            if key:
                header_map[key] = idx
        if not header_map:
            return []

        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{quoted_name}'!A2:ZZ1000",
        ).execute()
        rows = result.get("values", [])
        rules: List[ClassificationRule] = []
        for row in rows:
            def v(col: str) -> str:
                idx = header_map.get(col)
                if idx is None or idx >= len(row):
                    return ""
                return (row[idx] or "").strip()

            std = _to_standard_category(v("standard_category"))
            if not std:
                continue
            keywords = _split_keywords(v("title_keywords_include"))
            if not keywords:
                continue
            enabled = _parse_bool(v("enabled"), True)
            priority = _parse_int(v("priority"), 100)
            if not enabled:
                continue

            rules.append(
                ClassificationRule(
                    standard_category=std,
                    title_keywords_include=keywords,
                    priority=priority,
                    enabled=enabled,
                )
            )

        rules.sort(key=lambda r: r.priority)
        return rules
    except Exception as exc:
        # 탭 이름이 정확히 일치하지 않을 때(대소문자/공백/언더스코어 차이) 자동 해석 재시도
        try:
            if _retried:
                print(f"[classifier] rule load failed: {exc}")
                return []
            credentials_path = sheet_source_mod.get_credentials_path(os.getcwd())
            service = sheet_source_mod.get_sheets_service(credentials_path)
            meta = service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                fields="sheets(properties(title))",
            ).execute()
            titles = [
                ((s.get("properties", {}) or {}).get("title") or "").strip()
                for s in meta.get("sheets", [])
            ]
            normalized_target = re.sub(r"[\s_]+", "", (sheet_name or "").strip().lower())
            resolved = ""
            for t in titles:
                nt = re.sub(r"[\s_]+", "", (t or "").strip().lower())
                if nt == normalized_target:
                    resolved = t
                    break
            if not resolved:
                for t in titles:
                    nt = re.sub(r"[\s_]+", "", (t or "").strip().lower())
                    if normalized_target and (normalized_target in nt or nt in normalized_target):
                        resolved = t
                        break
            if resolved:
                print(f"[classifier] sheet name fallback: '{sheet_name}' -> '{resolved}'")
                return _load_rules_from_sheet(
                    spreadsheet_id=spreadsheet_id,
                    sheet_name=resolved,
                    _retried=True,
                )
            print(f"[classifier] rule load failed: {exc}")
            print(f"[classifier] available sheets: {titles}")
            return []
        except Exception as meta_exc:
            print(f"[classifier] rule load failed: {exc}")
            print(f"[classifier] metadata fallback failed: {meta_exc}")
            return []


def _get_rules(
    *,
    spreadsheet_id: str,
    sheet_name: str,
) -> List[ClassificationRule]:
    now = datetime.now()
    loaded_at = _RULE_CACHE.get("loaded_at")
    cache_key = f"{spreadsheet_id}::{sheet_name}"
    if (
        isinstance(loaded_at, datetime)
        and _RULE_CACHE.get("key") == cache_key
        and now - loaded_at < timedelta(seconds=_CACHE_TTL_SECONDS)
    ):
        return list(_RULE_CACHE.get("rules", []))

    rules = _load_rules_from_sheet(spreadsheet_id=spreadsheet_id, sheet_name=sheet_name)
    _RULE_CACHE["loaded_at"] = now
    _RULE_CACHE["key"] = cache_key
    _RULE_CACHE["rules"] = list(rules)
    return rules


def classify_standard_category_from_sheet(
    *,
    musinsa_large: str,
    musinsa_middle: str,
    musinsa_small: str,
    product_name: str,
    sheet_name: str = DEFAULT_CLASSIFIER_SHEET,
) -> Tuple[Optional[StandardCategory], Dict[str, str]]:
    """Return (standard_category_or_none, debug_meta)."""
    spreadsheet_id = _resolve_spreadsheet_id_from_runtime()
    if not spreadsheet_id:
        return None, {"reason": "no_spreadsheet_id"}

    rules = _get_rules(spreadsheet_id=spreadsheet_id, sheet_name=sheet_name)
    if not rules:
        return None, {"reason": "no_rules"}

    combined_text = build_combined_text(
        musinsa_large or "",
        musinsa_middle or "",
        musinsa_small or "",
        product_name or "",
    )
    if not combined_text:
        return None, {"reason": "empty_text"}

    matched_rule: Optional[ClassificationRule] = None
    matched_keyword = ""
    text = _normalize_text(combined_text)
    for rule in rules:
        for kw in rule.title_keywords_include:
            k = _normalize_text(kw)
            if k and k in text:
                matched_rule = rule
                matched_keyword = kw
                break
        if matched_rule:
            break

    if not matched_rule:
        return None, {"reason": "no_match"}

    return matched_rule.standard_category, {
        "reason": "matched",
        "matched_keyword": matched_keyword,
        "sheet_name": sheet_name,
        "standard_category": matched_rule.standard_category.value,
    }
