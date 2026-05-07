"""Sheet-driven StandardCategory classifier (minimal additive layer).

Reads keyword rules from Google Sheet and returns StandardCategory when matched.
If unavailable or unmatched, caller should fall back to existing resolver.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import logging
import os
import re
from typing import Dict, List, Optional, Tuple

from config.config_service import load_config as load_profile_config
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
_LOGGER = logging.getLogger(__name__)
_UNRESOLVED_JSONL_PATH = os.path.join("logs", "category_unresolved.jsonl")
_REMOVE_WORDS = [
    "\ubb34\ub8cc\ubc30\uc1a1", "\ub2f9\uc77c\ucd9c\uace0", "\uc815\ud488", "\uacf5\uc2dd", "1+1", "\uc138\uc77c",
    "\ud2b9\uac00", "\uc774\ubca4\ud2b8", "\ud560\uc778", "\ucd94\ucc9c", "\uc2e0\uc0c1",
]


@dataclass
class ClassificationRule:
    standard_category: StandardCategory
    title_keywords_include: List[str]
    priority: int = 100
    enabled: bool = True


CATEGORY_FALLBACK_RULES: List[Tuple[str, List[str], StandardCategory]] = [
    ("long_sleeve_tshirt", ["긴팔", "long sleeve", "ls tee"], StandardCategory.TOP_LONG_SLEEVE),
    ("short_sleeve_tshirt", ["반팔", "short sleeve", "t-shirt", "tee"], StandardCategory.TOP_TSHIRT),
    ("shorts", ["숏팬츠", "반바지", "shorts", "short pants", "half pants"], StandardCategory.PANTS_SHORTS),
    ("denim_pants", ["청바지", "denim", "jeans"], StandardCategory.PANTS_DENIM),
    ("jogger_pants", ["조거", "jogger", "sweatpants", "track pants"], StandardCategory.PANTS_JOGGER),
    ("sneakers", ["sneakers", "sneaker", "운동화", "스니커즈"], StandardCategory.SHOES_SNEAKER),
    ("sports_shoes", ["인도어화", "스포츠화", "코트화", "풋살화", "배드민턴화", "핸드볼화"], StandardCategory.SHOES_SNEAKER),
    ("sandals", ["슬리퍼", "샌들", "sandal", "slide"], StandardCategory.SHOES_SANDAL),
    ("hoodie", ["hoodie", "후드", "후디", "맨투맨", "sweatshirt"], StandardCategory.TOP_HOODIE),
    ("dress", ["dress", "드레스", "원피스"], StandardCategory.DRESS),
    ("skirt", ["skirt", "스커트"], StandardCategory.SKIRT_LONG),
    ("cardigan", ["cardigan", "가디건"], StandardCategory.TOP_CARDIGAN),
    ("knit", ["knit", "sweater", "니트", "스웨터"], StandardCategory.TOP_KNIT),
    ("shirt_blouse", ["shirt", "blouse", "셔츠", "블라우스"], StandardCategory.TOP_SHIRT),
    ("coat", ["coat", "코트"], StandardCategory.OUTER_COAT),
    ("padding", ["padding", "puffer", "down jacket", "패딩"], StandardCategory.OUTER_PADDING),
    ("jacket", ["jacket", "자켓", "재킷"], StandardCategory.OUTER_JACKET),
    ("bag", ["bag", "백", "토트", "숄더백", "crossbody"], StandardCategory.BAG_SHOULDER),
    ("cap", ["cap", "hat", "beanie", "모자", "비니"], StandardCategory.ACC_CAP),
    ("belt", ["belt", "벨트"], StandardCategory.ACC_BELT),
    ("sunglasses", ["sunglasses", "선글라스"], StandardCategory.ACC_EYEWEAR),
    ("socks", ["socks", "sock", "양말"], StandardCategory.INNER_UNDERWEAR),
    ("homewear", ["홈웨어", "homewear", "lounge wear", "loungewear", "잠옷", "파자마", "pajama"], StandardCategory.HOME_PAJAMA),
    ("innerwear", ["이너", "이너프리", "inner", "innerwear", "underwear", "속옷", "속바지", "브라", "bra", "팬티", "panty", "panties", "padded"], StandardCategory.INNER_UNDERWEAR),
    ("seamless_innerwear", ["심리스", "seamless", "seamless inner", "심리스 이너"], StandardCategory.INNER_UNDERWEAR),
    ("leggings", ["레깅스", "leggings", "legging"], StandardCategory.PANTS_LEGGINGS),
    ("loafer", ["loafer"], StandardCategory.SHOES_LOAFER),
]

FORCE_CATEGORY_MAP: Dict[Tuple[str, ...], StandardCategory] = {
    ("골반뽕", "힙업", "볼륨업", "보정", "보정속옷", "shaper", "shapewear"): StandardCategory.INNER_UNDERWEAR,
    ("심리스", "seamless", "심리스브라", "seamlessbra"): StandardCategory.INNER_UNDERWEAR,
    ("이너프리", "innerfree", "inner", "이너", "innerwear", "underwear"): StandardCategory.INNER_UNDERWEAR,
    ("bra", "브라", "sports bra", "sportsbra", "padded", "panty", "panties", "팬티"): StandardCategory.INNER_UNDERWEAR,
    ("홈웨어", "homewear", "잠옷", "파자마", "pajama", "loungewear", "lounge wear"): StandardCategory.HOME_PAJAMA,
    ("인도어화", "스포츠화", "코트화", "풋살화", "배드민턴화", "핸드볼화", "실내화"): StandardCategory.SHOES_SNEAKER,
}

MUSINSA_CATEGORY_OVERRIDES: List[Tuple[Tuple[str, ...], StandardCategory]] = [
    (("바지", "반바지"), StandardCategory.PANTS_SHORTS),
    (("팬츠", "반바지"), StandardCategory.PANTS_SHORTS),
    (("bottom", "short"), StandardCategory.PANTS_SHORTS),
    (("pants", "short"), StandardCategory.PANTS_SHORTS),
]


def _normalize_text(text: str) -> str:
    value = (text or "").lower().strip()
    for sep in ["/", "\\", "|", ",", ";", "_", "-", "(", ")", "[", "]"]:
        value = value.replace(sep, " ")
    return " ".join(value.split())


def normalize_product_name(text: str) -> str:
    value = (text or "").lower()
    value = re.sub(r"\(.*?\)", " ", value)
    value = re.sub(r"\[.*?\]", " ", value)
    value = re.sub(r"\b\d+\+?\d*\b", " ", value)
    for word in _REMOVE_WORDS:
        value = value.replace(word.lower(), " ")
    value = re.sub(r"[^a-z0-9가-힣\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _contains_keyword(text: str, keyword: str) -> bool:
    text_norm = (text or "").lower()
    keyword_norm = (keyword or "").lower()
    if not text_norm or not keyword_norm:
        return False
    if keyword_norm in text_norm:
        return True
    compact_text = text_norm.replace(" ", "")
    compact_keyword = keyword_norm.replace(" ", "")
    if compact_keyword and compact_keyword in compact_text:
        return True
    tokens = text_norm.split()
    return any(compact_keyword in token.replace(" ", "") for token in tokens if token)


def _resolve_from_musinsa_category_text(text: str) -> Optional[StandardCategory]:
    normalized = _normalize_text(text)
    compact = normalized.replace(" ", "")
    for keywords, category in MUSINSA_CATEGORY_OVERRIDES:
        if all(_contains_keyword(normalized, keyword) or keyword.replace(" ", "") in compact for keyword in keywords):
            return category
    return None


def fallback_category(name: str, brand: str) -> str:
    clean_name = normalize_product_name(name)
    text = _normalize_text(f"{clean_name} {brand}")
    for category_label, keywords, _standard in CATEGORY_FALLBACK_RULES:
        if any(_normalize_text(keyword) in text for keyword in keywords):
            return category_label
    return "湲고?"


def classify_category_with_reason(
    name: str,
    brand: str,
    existing_category: Optional[StandardCategory] = None,
) -> Tuple[StandardCategory, str]:
    clean_name = normalize_product_name(name)
    force_text = f"{clean_name} {(brand or '').lower()}".strip()
    result: StandardCategory | None = None
    reason = "unresolved"

    # If the caller already resolved a concrete category from sheet/mapping,
    # keep it as highest priority to avoid accidental force-map overrides
    # (e.g. shorts being flipped to homewear by noisy keywords).
    if existing_category is not None and existing_category != StandardCategory.ETC:
        return existing_category, "existing_category"

    # Guardrail: explicit dress/one-piece signals should win over noisy top keywords.
    dress_tokens = ("원피스", "드레스", "onepiece", "one-piece", "shirt dress", "dress")
    skirt_tokens = ("스커트", "치마", "skirt")
    has_dress = any(_contains_keyword(force_text, token) for token in dress_tokens)
    has_skirt = any(_contains_keyword(force_text, token) for token in skirt_tokens)
    if has_dress and not has_skirt:
        return StandardCategory.DRESS, "dress_keyword_override"

    # Guardrail: denim/jeans product names should not be flipped to innerwear
    # by broad body-shape keywords such as "골반뽕", "볼륨업".
    denim_tokens = ("청바지", "데님", "jeans", "denim", "부츠컷", "bootcut")
    if any(_contains_keyword(force_text, token) for token in denim_tokens):
        return StandardCategory.PANTS_DENIM, "denim_keyword_override"

    for keywords, category in FORCE_CATEGORY_MAP.items():
        if any(_contains_keyword(force_text, keyword) for keyword in keywords):
            result = category
            reason = "force_map"
            break

    if result is None:
        if existing_category is not None:
            result = existing_category
            reason = "existing_category"
        else:
            label = fallback_category(clean_name, brand)
            matched = next((std for cat, _kw, std in CATEGORY_FALLBACK_RULES if cat == label), None)
            result = matched or StandardCategory.ETC
            reason = "fallback_rules" if matched else "unresolved"

    return result, reason


def classify_category(name: str, brand: str, existing_category: Optional[StandardCategory] = None) -> StandardCategory:
    result, _reason = classify_category_with_reason(name, brand, existing_category)
    _LOGGER.info(
        "category_classification product=%s brand=%s result=%s",
        (name or "").strip(),
        (brand or "").strip(),
        result.value,
    )
    if result == StandardCategory.ETC:
        _LOGGER.warning("category_unresolved product=%s brand=%s", (name or "").strip(), (brand or "").strip())
        _write_unresolved_jsonl(product_name=(name or "").strip(), brand=(brand or "").strip())
    return result


def _tokenize_unresolved(text: str) -> List[str]:
    normalized = normalize_product_name(text)
    raw = re.findall(r"[a-zA-Z]{3,}|[가-힣]{2,}", normalized)
    stopwords = {
        "black", "white", "ivory", "navy", "blue", "red",
        "new", "official", "authentic", "women", "men",
        "臾대즺諛곗넚", "?뺥뭹", "怨듭떇",
        "value", "移댁씤?ㅻ?", "kindame", "free", "volume", "hip",
    }
    return [token for token in raw if token not in stopwords]


def _write_unresolved_jsonl(*, product_name: str, brand: str, row: int = 0) -> None:
    try:
        os.makedirs(os.path.dirname(_UNRESOLVED_JSONL_PATH), exist_ok=True)
        payload = {
            "row": row,
            "product_name": product_name,
            "brand": brand,
            "tokens": _tokenize_unresolved(f"{product_name} {brand}"),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        with open(_UNRESOLVED_JSONL_PATH, "a", encoding="utf-8") as fp:
            fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        # 遺꾨쪟 濡쒖쭅? ?덈? 以묐떒?쒗궎吏 ?딅뒗??
        return


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


def _resolve_category_sheet_name(default_name: str = DEFAULT_CLASSIFIER_SHEET) -> str:
    try:
        profile_name = (os.environ.get("AUTO_SHOP_PROFILE") or "default").strip() or "default"
        config = load_profile_config(profile_name)
        tabs_cfg = ((config.get("spreadsheet") or {}).get("tabs") or {})
        configured = str(tabs_cfg.get("category") or "").strip()
        return configured or default_name
    except Exception:
        return default_name


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
        # 癒쇱? ??議댁옱 ?щ?瑜??뺤씤??range parse ?먮윭瑜??쇳븳??
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
        # ???대쫫???뺥솗???쇱튂?섏? ?딆쓣 ????뚮Ц??怨듬갚/?몃뜑?ㅼ퐫??李⑥씠) ?먮룞 ?댁꽍 ?ъ떆??
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
    brand: str = "",
    sheet_name: str = DEFAULT_CLASSIFIER_SHEET,
) -> Tuple[Optional[StandardCategory], Dict[str, str]]:
    """Return (standard_category_or_none, debug_meta)."""
    musinsa_category_text = build_combined_text(
        musinsa_large or "",
        musinsa_middle or "",
        musinsa_small or "",
        "",
    )
    category_override = _resolve_from_musinsa_category_text(musinsa_category_text)
    if category_override is not None:
        return category_override, {
            "reason": "musinsa_category_override",
            "standard_category": category_override.value,
        }

    spreadsheet_id = _resolve_spreadsheet_id_from_runtime()
    if not spreadsheet_id:
        fallback_std = classify_category(product_name, brand)
        return fallback_std, {"reason": "no_spreadsheet_id_fallback", "standard_category": fallback_std.value}

    resolved_sheet_name = sheet_name
    if sheet_name == DEFAULT_CLASSIFIER_SHEET:
        resolved_sheet_name = _resolve_category_sheet_name(DEFAULT_CLASSIFIER_SHEET)

    rules = _get_rules(spreadsheet_id=spreadsheet_id, sheet_name=resolved_sheet_name)
    if not rules and resolved_sheet_name != DEFAULT_CLASSIFIER_SHEET:
        rules = _get_rules(spreadsheet_id=spreadsheet_id, sheet_name=DEFAULT_CLASSIFIER_SHEET)
        resolved_sheet_name = DEFAULT_CLASSIFIER_SHEET
    if not rules:
        fallback_std = classify_category(product_name, brand)
        return fallback_std, {"reason": "no_rules_fallback", "standard_category": fallback_std.value}

    combined_text = build_combined_text(
        musinsa_large or "",
        musinsa_middle or "",
        musinsa_small or "",
        product_name or "",
    )
    if not combined_text:
        fallback_std = classify_category(product_name, brand)
        return fallback_std, {"reason": "empty_text_fallback", "standard_category": fallback_std.value}

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
        fallback_std = classify_category(product_name, brand)
        return fallback_std, {"reason": "no_match_fallback", "standard_category": fallback_std.value}

    resolved = classify_category(product_name, brand, matched_rule.standard_category)
    return resolved, {
        "reason": "matched",
        "matched_keyword": matched_keyword,
        "sheet_name": resolved_sheet_name,
        "standard_category": resolved.value,
    }
