"""BUYMA category and gender inference helpers."""

from __future__ import annotations

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import sys
from typing import Callable, Dict, List, Sequence, Tuple
from marketplace.buyma.standard_category import (
    STANDARD_CATEGORY_SPECS,
    StandardCategory,
    build_combined_text,
    explain_standard_category_mapping,
    get_standard_category_spec,
    map_standard_to_buyma_middle_and_subcategory,
    normalize_standard_category,
    resolve_standard_category,
    validate_buyma_category_path,
)
from marketplace.common.category_classifier import classify_standard_category_from_sheet
import standard_category_map as standard_category_map_mod

try:
    from rapidfuzz import fuzz, process
except Exception:  # pragma: no cover - exercised when rapidfuzz is unavailable.
    fuzz = None
    process = None


def _safe_log(message: str) -> None:
    try:
        print(message)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        encoded = (message or "").encode(encoding, errors="replace")
        print(encoded.decode(encoding, errors="replace"))


FEMALE_KEYWORDS = [
    "women", "woman", "female", "lady", "ladies", "girl", "girls",
    "여성", "여자", "우먼", "레이디", "걸", "숙녀",
]
MALE_KEYWORDS = [
    "men", "man", "male", "gentleman", "boy", "boys",
    "남성", "남자", "맨", "보이", "신사",
]
BUYMA_GENDER_CATEGORY_MAP = {
    "F": "レディースファッション",
    "M": "メンズファッション",
    "U": "メンズファッション",
}

CATEGORY_KEYWORDS = [
    (["티셔츠", "반팔", "긴팔", "tee", "t-shirt"], None, "トップス", "Tシャツ・カットソー"),
    (["후드", "hoodie", "hood"], None, "トップス", "パーカー・フーディ"),
    (["맨투맨", "sweatshirt", "sweat"], None, "トップス", "スウェット"),
    (["셔츠", "shirt", "blouse"], None, "トップス", "シャツ"),
    (["니트", "sweater", "knit"], None, "トップス", "ニット・セーター"),
    (["청바지", "데님", "jeans", "denim"], None, "ボトムス", "デニム・ジーンズ"),
    (["슬랙스", "trousers"], None, "ボトムス", "スラックス"),
    (["팬츠", "바지", "pants"], None, "ボトムス", "パンツ"),
    (["반바지", "shorts"], None, "ボトムス", "ショーツ"),
    (["원피스", "dress"], None, "ワンピース", ""),
    (["자켓", "재킷", "jacket"], None, "アウター", "ジャケット"),
    (["코트", "coat"], None, "アウター", "コート"),
    (["가디건", "cardigan"], None, "アウター", "カーディガン"),
    (["바람막이", "windbreaker"], None, "アウター", "ナイロンジャケット"),
    (["운동화", "스니커즈", "sneaker"], None, "靴", "スニーカー"),
    (["샌들", "sandal"], None, "靴", "サンダル"),
    (["부츠", "boot"], None, "靴", "ブーツ"),
    (["로퍼", "loafer"], None, "靴", "ローファー"),
]

CATEGORY_RECOVERY_ALIASES: Dict[str, List[str]] = {
    "スウェット・トレーナー": ["スウェット", "トレーナー"],
    "Tシャツ・カットソー": ["カットソー", "Tシャツ"],
    "パーカー・フーディ": ["パーカー", "フーディー", "フーディ"],
    "ブラウス・シャツ": ["ブラウス", "シャツ"],
    "ダウンジャケット・コート": ["ダウンジャケット", "ダウンコート", "ダウン"],
    "レザージャケット・コート": ["レザージャケット", "レザーアウター"],
    "デニム・ジーパン": ["デニム・ジーンズ", "ジーンズ", "デニムパンツ"],
    "ショートパンツ": ["ショーツ", "ハーフ・ショートパンツ"],
    "スウェットパンツ": ["トラックパンツ", "ジョガーパンツ"],
    "ローファー・オックスフォード": ["ローファー", "オックスフォード"],
    "サンダル・ミュール": ["サンダル", "ミュール"],
    "ドレスシューズ・革靴・ビジネスシューズ": ["ドレスシューズ", "革靴", "ビジネスシューズ"],
    "バックパック・リュック": ["バックパック", "リュック"],
    "ニットキャップ・ビーニー": ["ニットキャップ", "ビーニー"],
    "マフラー・ストール": ["マフラー", "ストール", "スカーフ"],
}

COMMON_PARENT_FALLBACK_MIDDLES: Dict[str, List[str]] = {
    "レディースファッション": ["トップス", "アウター", "ボトムス", "ワンピース・オールインワン", "靴・シューズ", "バッグ・カバン", "ファッション雑貨・小物"],
    "メンズファッション": ["トップス", "アウター・ジャケット", "パンツ・ボトムス", "靴・ブーツ・サンダル", "バッグ・カバン", "ファッション雑貨・小物", "その他ファッション"],
}


def detect_gender_raw(title: str) -> str:
    text = (title or "").lower()
    if any(keyword in text for keyword in FEMALE_KEYWORDS):
        return "F"
    if any(keyword in text for keyword in MALE_KEYWORDS):
        return "M"
    return "U"


def convert_gender_for_buyma(gender: str) -> str:
    if gender == "F":
        return "レディース"
    if gender == "M":
        return "メンズ"
    return "メンズ"


def detect_gender(title: str) -> str:
    return convert_gender_for_buyma(detect_gender_raw(title))


def get_buyma_fashion_category_from_gender(title: str) -> str:
    raw_gender = detect_gender_raw(title)
    return BUYMA_GENDER_CATEGORY_MAP.get(raw_gender, BUYMA_GENDER_CATEGORY_MAP["U"])


def infer_buyma_category(product_name_kr: str, product_name_en: str, brand: str = "") -> Tuple[str, str, str]:
    title = f"{product_name_kr} {product_name_en}".strip()
    text = f"{product_name_kr} {product_name_en} {brand}".lower()
    fashion_category = get_buyma_fashion_category_from_gender(title)
    if any(token in text for token in ["new balance", "뉴발란스", "mr530", "530lg", "530sg", "530ka", "m1906", "1906r", "2002r", "327", "990v", "991", "992", "993"]):
        return (fashion_category, "靴", "スニーカー")
    for keywords, cat1, cat2, cat3 in CATEGORY_KEYWORDS:
        if any(keyword.lower() in text for keyword in keywords):
            if cat1 is None:
                cat1 = fashion_category
            return (cat1, cat2 or "", cat3 or "")
    return ("", "", "")


def normalize_sheet_category_labels(cat1: str, cat2: str, cat3: str) -> Tuple[str, str, str]:
    c1 = (cat1 or "").strip()
    c2 = (cat2 or "").strip()
    c3 = (cat3 or "").strip()

    top_map = {
        "여성": "レディースファッション",
        "여자": "レディースファッション",
        "레이디스": "レディースファッション",
        "레ディース": "レディースファッション",
        "남성": "メンズファッション",
        "남자": "メンズファッション",
        "멘즈": "メンズファッション",
        "メンズ": "メンズファッション",
        "レディース": "レディースファッション",
    }
    mid_map = {
        "상의": "トップス",
        "하의": "ボトムス",
        "바지": "ボトムス",
        "신발": "靴",
        "슈즈": "靴",
        "운동화": "靴",
        "아우터": "アウター",
        "가방": "バッグ",
        "악세서리": "アクセサリー",
        "악세사리": "アクセサリー",
        "원피스": "ワンピース",
    }
    sub_map = {
        "데님 팬츠": "デニム・ジーンズ",
        "데님팬츠": "デニム・ジーンズ",
        "청바지": "デニム・ジーンズ",
        "슬랙스": "スラックス",
        "팬츠": "パンツ",
        "조거팬츠": "ジョガーパンツ",
        "카고팬츠": "カーゴパンツ",
        "반바지": "ショーツ",
        "스니커즈": "スニーカー",
        "러닝화": "ランニングシューズ",
        "샌들": "サンダル",
        "부츠": "ブーツ",
        "로퍼": "ローファー",
        "티셔츠": "Tシャツ・カットソー",
        "후드": "パーカー・フーディ",
        "후드티": "パーカー・フーディ",
        "맨투맨": "スウェット",
        "셔츠": "シャツ",
        "니트": "ニット・セーター",
        "코트": "コート",
        "자켓": "ジャケット",
        "블레이저": "テーラードジャケット",
        "가디건": "カーディガン",
        "바람막이": "ナイロンジャケット",
    }

    return top_map.get(c1, c1), mid_map.get(c2, c2), sub_map.get(c3, c3)


def normalize_gender_label_for_sheet(text: str) -> str:
    value = (text or "").strip().lower()
    if not value:
        return ""
    if value in {"여성", "여자", "레ディース", "レディース", "w", "female", "women", "womens"}:
        return "여성"
    if value in {"남성", "남자", "メンズ", "m", "male", "men", "mens"}:
        return "남성"
    if "여성" in value or "レディース" in value or "women" in value or "female" in value:
        return "여성"
    if "남성" in value or "メンズ" in value or "men" in value or "male" in value:
        return "남성"
    return ""


def remap_sheet_categories_with_gender(cat1: str, cat2: str, cat3: str) -> Tuple[str, str, str]:
    values = [(cat1 or "").strip(), (cat2 or "").strip(), (cat3 or "").strip()]
    gender = ""
    rest: List[str] = []
    for value in values:
        if not value:
            continue
        normalized_gender = normalize_gender_label_for_sheet(value)
        if normalized_gender and not gender:
            gender = normalized_gender
            continue
        if normalized_gender:
            continue
        rest.append(value)

    if not gender:
        return cat1, cat2, cat3
    new_mid = rest[0] if len(rest) > 0 else ""
    new_small = rest[1] if len(rest) > 1 else ""
    return gender, new_mid, new_small


def build_buyma_category_plan(
    row_data: Dict[str, str],
    *,
    category_corrector: Callable[[str, str, str], str],
) -> Dict[str, str]:
    """Build category selection plan from source row without browser access."""
    sheet_cat1 = (row_data.get("musinsa_category_large") or "").strip()
    sheet_cat2 = (row_data.get("musinsa_category_middle") or "").strip()
    sheet_cat3 = (row_data.get("musinsa_category_small") or "").strip()
    sheet_cat1, sheet_cat2, sheet_cat3 = remap_sheet_categories_with_gender(sheet_cat1, sheet_cat2, sheet_cat3)

    product_name_kr = row_data.get("product_name_kr", "")
    product_name_en = row_data.get("product_name_en", "")
    brand = row_data.get("brand", "")

    if sheet_cat1 and sheet_cat2:
        cat1, cat2, cat3 = normalize_sheet_category_labels(sheet_cat1, sheet_cat2, sheet_cat3)
        cat_source = "시트(W/X/Y)"
    else:
        cat1, cat2, cat3 = infer_buyma_category(product_name_kr, product_name_en, brand)
        cat_source = "자동추론"

    musinsa_category_text = " / ".join([sheet_cat1, sheet_cat2, sheet_cat3]).strip(" /")
    source_product_name = product_name_kr or product_name_en or ""

    combined_text = build_combined_text(
        sheet_cat1,
        sheet_cat2,
        sheet_cat3,
        source_product_name,
    )
    classifier_std, classifier_meta = classify_standard_category_from_sheet(
        musinsa_large=sheet_cat1,
        musinsa_middle=sheet_cat2,
        musinsa_small=sheet_cat3,
        product_name=source_product_name,
    )
    if classifier_std is not None:
        standard_category = classifier_std
        _safe_log(
            f"  [category][classifier] matched standard={standard_category.value} "
            f"keyword={classifier_meta.get('matched_keyword', '')}"
        )
    else:
        standard_category, combined_text = resolve_standard_category(
            sheet_cat1,
            sheet_cat2,
            sheet_cat3,
            source_product_name,
        )
        _safe_log(f"  [category][classifier] fallback reason={classifier_meta.get('reason', 'unknown')}")
    is_mens_category = "メンズ" in (cat1 or "")
    # Prefer table-based mapping layer first; keep existing semantic mapper as fallback.
    mapped_parent, mapped_cat2, mapped_cat3 = standard_category_map_mod.resolve_standard_category_buyma_target(
        standard_category,
        is_mens=is_mens_category,
        combined_text=combined_text,
    )
    # 방어 로직: 매핑표가 child 값을 middle에 넣은 경우(예: パーカー・フーディ > パーカー・フーディ)
    # legacy middle/child 조합으로 자동 보정해 UI 선택 실패를 줄인다.
    if mapped_cat2 and mapped_cat3 and mapped_cat2 == mapped_cat3:
        legacy_mid, legacy_child = map_standard_to_buyma_middle_and_subcategory(
            standard_category,
            combined_text,
            is_mens=is_mens_category,
        )
        if legacy_mid:
            mapped_cat2 = legacy_mid
        if legacy_child:
            mapped_cat3 = legacy_child
    # 중카테가 비어있거나(또는 child label과 동일/유사한 경우) standard 기반 기본 중카테로 교정
    norm_cat2 = _normalize_option_text(mapped_cat2)
    norm_cat3 = _normalize_option_text(mapped_cat3)
    if (not mapped_cat2) or (norm_cat2 and norm_cat3 and norm_cat2 == norm_cat3):
        default_mid = _default_middle_for_standard(standard_category.value, is_mens=is_mens_category)
        if default_mid:
            mapped_cat2 = default_mid
    mapping_source = standard_category_map_mod.get_runtime_mapping_source()
    mapping_row_source = standard_category_map_mod.get_resolved_mapping_row_source(
        standard_category,
        is_mens=is_mens_category,
    )
    mapping_valid = validate_buyma_category_path(mapped_parent, mapped_cat2, mapped_cat3)
    mapping_table_used = standard_category != StandardCategory.ETC and bool(mapped_cat2) and mapping_valid

    legacy_cat2, legacy_cat3 = "", ""
    if not mapping_table_used:
        legacy_cat2, legacy_cat3 = map_standard_to_buyma_middle_and_subcategory(
            standard_category,
            combined_text,
            is_mens=is_mens_category,
        )
    legacy_valid = validate_buyma_category_path(cat1, legacy_cat2, legacy_cat3)
    legacy_used = standard_category != StandardCategory.ETC and bool(legacy_cat2) and legacy_valid
    semantic_fallback_used = not mapping_table_used

    if mapping_table_used:
        if mapped_parent:
            cat1 = mapped_parent
        cat2 = mapped_cat2
        cat3 = mapped_cat3
        cat_source = f"{cat_source}+stdmap"
    elif legacy_used:
        cat2 = legacy_cat2
        cat3 = legacy_cat3
        cat_source = f"{cat_source}+legacy-semantic"

    corrected_cat3 = category_corrector(cat3, source_product_name, musinsa_category_text)
    fallback_cat1, fallback_cat2, fallback_cat3 = infer_buyma_category(product_name_kr, product_name_en, brand)
    corrected_fallback_cat3 = category_corrector(
        fallback_cat3,
        source_product_name,
        musinsa_category_text,
    )
    final_path_valid = validate_buyma_category_path(cat1, cat2, corrected_cat3)
    mapping_diag = explain_standard_category_mapping(standard_category, is_mens=is_mens_category)

    _safe_log(f"  [category][semantic] musinsa={sheet_cat1} / {sheet_cat2} / {sheet_cat3}")
    _safe_log(f"  [category][semantic] product_name={source_product_name}")
    _safe_log(f"  [category][semantic] combined_text={combined_text}")
    _safe_log(f"  [category][semantic] standard_category={standard_category.value}")
    _safe_log(f"  [category][semantic] mapped_buyma={cat1} > {cat2} > {corrected_cat3}")
    _safe_log(f"  [category][semantic] spec_buyma={mapping_diag.get('buyma_parent')} > {mapping_diag.get('buyma_middle')} > {mapping_diag.get('buyma_child')}")
    _safe_log(f"  [category][semantic] validator_passed={final_path_valid}")
    _safe_log(f"  [category][semantic] mapping_table_used={mapping_table_used}")
    _safe_log(f"  [category][semantic] mapping_source={mapping_source}")
    _safe_log(f"  [category][semantic] mapping_row_source={mapping_row_source}")
    _safe_log(f"  [category][semantic] legacy_used={legacy_used}")
    _safe_log(f"  [category][semantic] fallback_used={semantic_fallback_used}")

    return {
        "sheet_cat1": sheet_cat1,
        "sheet_cat2": sheet_cat2,
        "sheet_cat3": sheet_cat3,
        "cat1": cat1,
        "cat2": cat2,
        "cat3": corrected_cat3,
        "cat_source": cat_source,
        "musinsa_category_text": musinsa_category_text,
        "source_product_name": source_product_name,
        "combined_text": combined_text,
        "standard_category": standard_category.value,
        "mapping_table_used": mapping_table_used,
        "mapping_source": mapping_source,
        "mapping_row_source": mapping_row_source,
        "legacy_used": legacy_used,
        "semantic_fallback_used": semantic_fallback_used,
        "category_path_valid": final_path_valid,
        "mapping_validator_passed": mapping_valid,
        "fallback_cat1": fallback_cat1,
        "fallback_cat2": fallback_cat2,
        "fallback_cat3": corrected_fallback_cat3,
    }


def _dedupe_keep_order(values: Sequence[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        item = (value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _category_recovery_aliases(label: str) -> List[str]:
    return _dedupe_keep_order(CATEGORY_RECOVERY_ALIASES.get((label or "").strip(), []))


def _category_recovery_candidates(
    category_plan: Dict[str, str],
    item_index: int,
    *,
    parent: str,
    middle: str = "",
) -> List[str]:
    is_mens = "メンズ" in (parent or category_plan.get("cat1", ""))
    standard_category = normalize_standard_category(str(category_plan.get("standard_category", "") or ""))
    spec = get_standard_category_spec(standard_category)
    candidates: List[str] = []

    if item_index == 1:
        if spec:
            candidates.append(spec.middle(is_mens=is_mens))
        candidates.extend(COMMON_PARENT_FALLBACK_MIDDLES.get(parent or category_plan.get("cat1", ""), []))
        for other_spec in STANDARD_CATEGORY_SPECS.values():
            candidates.append(other_spec.middle(is_mens=is_mens))
    elif item_index == 2:
        if spec:
            candidates.append(spec.child)
        target_middle = middle or category_plan.get("cat2", "")
        for other_spec in STANDARD_CATEGORY_SPECS.values():
            if other_spec.middle(is_mens=is_mens) == target_middle:
                candidates.append(other_spec.child)

    return _dedupe_keep_order([value for value in candidates if value and "その他" not in value])


def _best_fuzzy_match(target: str, candidates: Sequence[str], *, threshold: int = 78) -> Tuple[str, int]:
    target = (target or "").strip()
    choices = _dedupe_keep_order(candidates)
    if not target or not choices:
        return "", 0
    if process is not None and fuzz is not None:
        found = process.extractOne(target, choices, scorer=fuzz.WRatio)
        if not found:
            return "", 0
        label, score = str(found[0]), int(found[1])
        return (label, score) if score >= threshold else ("", score)

    import difflib

    scored = [(candidate, int(difflib.SequenceMatcher(None, target, candidate).ratio() * 100)) for candidate in choices]
    label, score = max(scored, key=lambda item: item[1])
    return (label, score) if score >= threshold else ("", score)


def _read_selected_category_value(driver, item_index: int) -> str:
    try:
        return str(
            driver.execute_script(
                """
                var items = document.querySelectorAll('.sell-category__item');
                if (arguments[0] === 0) {
                    var root = document.querySelector('.sell-category-select');
                    var v0 = root ? root.querySelector('.Select-value-label') : null;
                    return v0 ? v0.textContent.trim() : '';
                }
                if (items.length <= arguments[0]) return '';
                var v = items[arguments[0]].querySelector('.Select-value-label');
                return v ? v.textContent.trim() : '';
                """,
                item_index,
            )
            or ""
        ).strip()
    except Exception:
        return ""


def _try_category_recovery(
    driver,
    category_plan: Dict[str, str],
    diag: Dict[str, object],
    *,
    item_index: int,
    target_label: str,
    parent: str,
    middle: str = "",
    find_best_option_by_arrow: Callable[[object, int, str, bool], bool],
) -> Tuple[bool, str]:
    level_name = "middle" if item_index == 1 else "child"
    target_label = (target_label or "").strip()
    attempts: List[Dict[str, object]] = diag.setdefault("recovery_attempts", [])  # type: ignore[assignment]

    def _attempt(method: str, label: str, score: int = 0, *, allow_other: bool = False) -> Tuple[bool, str]:
        if not label:
            return False, ""
        _safe_log(f"  [category][recovery] level={level_name} method={method} target={target_label} try={label} score={score}")
        ok = find_best_option_by_arrow(driver, item_index, label, allow_other)
        selected = _read_selected_category_value(driver, item_index) or label if ok else ""
        attempts.append({"level": level_name, "method": method, "target": target_label, "candidate": label, "score": score, "success": ok, "selected": selected})
        if ok:
            diag["recovery_used"] = True
            diag["recovery_method"] = method
            diag[f"recovered_{level_name}_category"] = selected
            _safe_log(f"  [category][recovery] success level={level_name} method={method} selected={selected}")
        return ok, selected

    for alias in _category_recovery_aliases(target_label):
        ok, selected = _attempt("alias", alias)
        if ok:
            return True, selected

    candidates = _category_recovery_candidates(category_plan, item_index, parent=parent, middle=middle)
    fuzzy_label, score = _best_fuzzy_match(target_label, candidates)
    if fuzzy_label and fuzzy_label != target_label:
        ok, selected = _attempt("fuzzy", fuzzy_label, score)
        if ok:
            return True, selected

    fallback_candidates = [candidate for candidate in candidates if candidate not in {target_label, fuzzy_label, *set(_category_recovery_aliases(target_label))}]
    for candidate in fallback_candidates[:8]:
        ok, selected = _attempt("same_parent_fallback", candidate)
        if ok:
            return True, selected

    ok, selected = _attempt("other", "その他", allow_other=False)
    if ok:
        diag["failure_stage"] = f"{level_name}_other"
        diag["final_result"] = "other"
        return True, selected
    return False, ""


def apply_buyma_category_selection(
    driver,
    category_plan: Dict[str, str],
    *,
    select_category_by_arrow: Callable[[object, int, str], bool],
    find_best_option_by_arrow: Callable[[object, int, str, bool], bool],
) -> Dict[str, object]:
    """Apply BUYMA category plan to the browser UI and return diagnostics."""
    cat1 = category_plan["cat1"]
    cat2 = category_plan["cat2"]
    cat3 = category_plan["cat3"]
    cat_source = category_plan["cat_source"]

    diag: Dict[str, object] = {
        "category_selection_success": False,
        "failure_stage": "",
        "final_result": "",
        "fallback_used": False,
        "standard_category": category_plan.get("standard_category", ""),
        "cat_source": category_plan.get("cat_source", ""),
        "semantic_fallback_used": bool(category_plan.get("semantic_fallback_used", False)),
        "target_buyma_parent_category": cat1,
        "target_buyma_middle_category": cat2,
        "target_buyma_child_category": cat3,
        "actual_selected_parent_category": "",
        "actual_selected_middle_category": "",
        "actual_selected_child_category": "",
        "mapping_table_used": bool(category_plan.get("mapping_table_used", False)),
        "legacy_used": bool(category_plan.get("legacy_used", False)),
        "category_path_valid": bool(category_plan.get("category_path_valid", False)),
        "mapping_validator_passed": bool(category_plan.get("mapping_validator_passed", False)),
        "recovery_used": False,
        "recovery_method": "",
        "recovered_middle_category": "",
        "recovered_child_category": "",
        "recovery_attempts": [],
    }

    if not cat1 or not cat2:
        print("  △ 카테고리 추론 불가, 수동 선택 필요")
        diag["failure_stage"] = "plan_invalid"
        diag["final_result"] = "failed"
        return diag

    print(f"  카테고리({cat_source}): {cat1} > {cat2} > {cat3}")
    selected_cat1 = select_category_by_arrow(driver, 0, cat1)
    if not selected_cat1:
        selected_cat1 = find_best_option_by_arrow(driver, 0, cat1, False)

    if (not selected_cat1) and cat_source.startswith("시트"):
        f1 = category_plan["fallback_cat1"]
        f2 = category_plan["fallback_cat2"]
        f3 = category_plan["fallback_cat3"]
        if f1 and f2:
            print(f"  △ 시트 카테고리 미매칭, 자동추론 fallback: {f1} > {f2} > {f3}")
            cat1, cat2, cat3 = f1, f2, f3
            diag["fallback_used"] = True
            diag["target_buyma_parent_category"] = cat1
            diag["target_buyma_middle_category"] = cat2
            diag["target_buyma_child_category"] = cat3
            selected_cat1 = select_category_by_arrow(driver, 0, cat1)
            if not selected_cat1:
                selected_cat1 = find_best_option_by_arrow(driver, 0, cat1, False)

    if not selected_cat1:
        print(f"  △ 대카테 '{cat1}' 미발견, 자동 선택 필요")
        print("  [category][parent] selection failed")
        diag["failure_stage"] = "parent"
        diag["final_result"] = "failed"
        return diag

    diag["actual_selected_parent_category"] = cat1
    print(f"  ✓ 대카테: {cat1}")
    if not cat2:
        print("  △ 중카테 없음, 수동 선택 필요")
        diag["failure_stage"] = "middle"
        diag["final_result"] = "failed"
        return diag

    if not find_best_option_by_arrow(driver, 1, cat2, False):
        print(f"  △ 중카테 '{cat2}' 직접 선택 실패, recovery 시작")
        recovered, recovered_value = _try_category_recovery(
            driver,
            category_plan,
            diag,
            item_index=1,
            target_label=cat2,
            parent=cat1,
            find_best_option_by_arrow=find_best_option_by_arrow,
        )
        if not recovered:
            print(f"  △ 중카테 '{cat2}' recovery 실패")
            diag["failure_stage"] = "middle"
            diag["final_result"] = "failed"
            return diag
        cat2 = recovered_value or cat2
        diag["target_buyma_middle_category"] = cat2

    sel_val = _read_selected_category_value(driver, 1)
    diag["actual_selected_middle_category"] = sel_val or cat2
    if "その他" in (sel_val or ""):
        print(f"  ✓ 중카테: {cat2} -> その他 (기타)")
        diag["failure_stage"] = "middle_other"
        diag["final_result"] = "other"
    else:
        print(f"  ✓ 중카테: {sel_val or cat2}")

    if not cat3:
        diag["category_selection_success"] = (diag["final_result"] == "success")
        if not diag["final_result"]:
            diag["final_result"] = "success"
        return diag

    items_count = len(driver.find_elements(By.CSS_SELECTOR, ".sell-category__item"))
    if items_count < 3:
        diag["category_selection_success"] = (diag["final_result"] == "success")
        if not diag["final_result"]:
            diag["final_result"] = "success"
        return diag

    if find_best_option_by_arrow(driver, 2, cat3, False):
        sel_val3 = _read_selected_category_value(driver, 2)
        diag["actual_selected_child_category"] = sel_val3 or cat3
        if "その他" in (sel_val3 or ""):
            print(f"  ✓ 소카테: {cat3} -> その他 (기타)")
            if not diag["failure_stage"]:
                diag["failure_stage"] = "child_other"
            diag["final_result"] = "other"
        else:
            print(f"  ✓ 소카테: {sel_val3 or cat3}")
    else:
        print(f"  △ 소카테 '{cat3}' 직접 선택 실패, recovery 시작")
        recovered, recovered_value = _try_category_recovery(
            driver,
            category_plan,
            diag,
            item_index=2,
            target_label=cat3,
            parent=cat1,
            middle=cat2,
            find_best_option_by_arrow=find_best_option_by_arrow,
        )
        if not recovered:
            print(f"  △ 소카테 '{cat3}' recovery 실패")
            diag["failure_stage"] = "child"
            diag["final_result"] = "failed"
            return diag
        diag["actual_selected_child_category"] = recovered_value or cat3
        diag["target_buyma_child_category"] = recovered_value or cat3

    diag["category_selection_success"] = (diag["final_result"] == "success")
    if not diag["final_result"]:
        diag["final_result"] = "success"
    return diag


def get_category_select_el(driver, item_index: int):
    """Return the React-Select element for a category level."""
    if item_index == 0:
        return driver.find_element(By.CSS_SELECTOR, ".sell-category-select")
    items = driver.find_elements(By.CSS_SELECTOR, ".sell-category__item")
    if len(items) <= item_index:
        return None
    return items[item_index].find_element(By.CSS_SELECTOR, ".Select")


def _category_stage_name(item_index: int) -> str:
    if item_index == 0:
        return "parent"
    if item_index == 1:
        return "middle"
    if item_index == 2:
        return "child"
    return f"level_{item_index}"


def _normalize_option_text(text: str) -> str:
    return (text or "").replace(" ", "").replace("\u3000", "").strip().lower()


def _extract_keyword_tokens(target: str) -> List[str]:
    text = (target or "").strip()
    if not text:
        return []
    replaced = text
    for sep in ["/", "-", "_", "・", ",", "(", ")", "[", "]"]:
        replaced = replaced.replace(sep, " ")
    tokens = [t.strip().lower() for t in replaced.split() if len(t.strip()) >= 2]
    if not tokens and text:
        tokens = [text.lower()]
    return list(dict.fromkeys(tokens))


def _default_middle_for_standard(standard_category: str, *, is_mens: bool) -> str:
    std = (standard_category or "").upper()
    if std.startswith("TOP_"):
        return "トップス"
    if std == "HOME_PAJAMA":
        return "インナー・ルームウェア"
    if std == "OUTER":
        return "アウター・ジャケット" if is_mens else "アウター"
    if std == "PANTS":
        return "パンツ・ボトムス" if is_mens else "ボトムス"
    if std == "SNEAKER":
        return "靴・ブーツ・サンダル" if is_mens else "靴・シューズ"
    if std == "DRESS":
        return "その他ファッション" if is_mens else "ワンピース・オールインワン"
    return ""


def _read_dropdown_options(driver, item_index: int) -> List[Dict[str, str]]:
    return driver.execute_script(
        """
        var opts = document.querySelectorAll(
            '.Select-menu-outer .Select-option, .Select-menu .Select-option, [role="listbox"] [role="option"]'
        );
        var rows = [];
        for (var i = 0; i < opts.length; i++) {
            var el = opts[i];
            rows.push({
                text: (el.textContent || '').trim(),
                aria: (el.getAttribute('aria-label') || '').trim(),
                value: (el.getAttribute('data-value') || el.getAttribute('value') || '').trim()
            });
        }
        return rows;
        """,
        item_index,
    ) or []


def _wait_for_dropdown_options(driver, item_index: int, *, sleep_fn, timeout_sec: float = 2.0) -> List[Dict[str, str]]:
    # open 이후 최소 200~500ms 대기 + 옵션 로딩 폴링
    sleep_fn(0.35)
    elapsed = 0.0
    step = 0.2
    options: List[Dict[str, str]] = []
    while elapsed <= timeout_sec:
        options = _read_dropdown_options(driver, item_index)
        if options:
            return options
        # 일부 React-Select은 ArrowDown 후에만 options DOM이 생성된다.
        try:
            sel = get_category_select_el(driver, item_index)
            if sel is not None:
                combo = sel.find_element(By.CSS_SELECTOR, ".Select-input > input, .Select-input")
                combo.send_keys(Keys.ARROW_DOWN)
        except Exception:
            pass
        sleep_fn(step)
        elapsed += step
    return options


def _log_dropdown_options(stage: str, target: str, options: List[Dict[str, str]]) -> None:
    print(f"  [category][{stage}] target='{target}' options={len(options)}")
    if not options:
        print(f"  [category][{stage}] options: []")
        return
    joined = " | ".join([(o.get("text") or o.get("aria") or o.get("value") or "").strip() for o in options])
    print(f"  [category][{stage}] options: {joined}")


def _choose_option_with_priority(options: List[Dict[str, str]], target: str) -> Dict[str, str] | None:
    if not options:
        return None
    target_raw = (target or "").strip()
    target_norm = _normalize_option_text(target_raw)
    tokens = _extract_keyword_tokens(target_raw)

    # 1) 완전 일치
    for opt in options:
        for cand in (opt.get("text", ""), opt.get("aria", ""), opt.get("value", "")):
            if _normalize_option_text(cand) == target_norm:
                return opt

    # 2) 부분 일치 (target in option or option in target)
    for opt in options:
        for cand in (opt.get("text", ""), opt.get("aria", ""), opt.get("value", "")):
            cand_norm = _normalize_option_text(cand)
            if target_norm and (target_norm in cand_norm or cand_norm in target_norm):
                return opt

    # 3) 키워드 포함
    if tokens:
        for token in tokens:
            token_norm = _normalize_option_text(token)
            for opt in options:
                for cand in (opt.get("text", ""), opt.get("aria", ""), opt.get("value", "")):
                    if token_norm and token_norm in _normalize_option_text(cand):
                        return opt
    return None


def _click_option_by_signature(driver, item_index: int, option: Dict[str, str], *, sleep_fn) -> bool:
    text = (option.get("text") or "").strip()
    aria = (option.get("aria") or "").strip()
    value = (option.get("value") or "").strip()
    clicked = driver.execute_script(
        """
        var opts = document.querySelectorAll('.Select-menu-outer .Select-option');
        var text = arguments[1] || '';
        var aria = arguments[2] || '';
        var value = arguments[3] || '';

        function norm(s) {
            return (s || '').replace(/\\s+/g, '').toLowerCase();
        }
        var textN = norm(text), ariaN = norm(aria), valueN = norm(value);
        for (var i = 0; i < opts.length; i++) {
            var el = opts[i];
            var t = norm(el.textContent || '');
            var a = norm(el.getAttribute('aria-label') || '');
            var v = norm(el.getAttribute('data-value') || el.getAttribute('value') || '');
            if ((valueN && v && v === valueN) || (ariaN && a && a === ariaN) || (textN && t && t === textN)) {
                el.click();
                return true;
            }
        }
        return false;
        """,
        item_index,
        text,
        aria,
        value,
    )
    if clicked:
        sleep_fn(1.2)
    return bool(clicked)


def select_category_by_typing(driver, item_index: int, target_label: str, *, sleep_fn, scroll_and_click) -> bool:
    """Type-filter a BUYMA category React-Select and choose the best match."""
    sel_el = get_category_select_el(driver, item_index)
    if sel_el is None:
        return False

    ctrl = sel_el.find_element(By.CSS_SELECTOR, ".Select-control")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", ctrl)
    sleep_fn(0.3)
    driver.execute_script("arguments[0].click()", ctrl)
    sleep_fn(0.6)

    combo = sel_el.find_element(By.CSS_SELECTOR, ".Select-input > input, .Select-input")
    combo.send_keys(target_label)
    sleep_fn(0.8)

    try:
        options = driver.find_elements(By.CSS_SELECTOR, ".Select-menu-outer .Select-option")
        exact = next((o for o in options if o.text.strip() == target_label), None)
        partial = next((o for o in options if target_label in o.text), None)
        chosen = exact or partial
        if chosen:
            scroll_and_click(driver, chosen)
            sleep_fn(1.5)
            return True
    except Exception:
        pass

    try:
        for _ in range(len(target_label)):
            combo.send_keys(Keys.BACK_SPACE)
        sleep_fn(0.2)
    except Exception:
        pass

    driver.execute_script("arguments[0].click()", ctrl)
    sleep_fn(0.6)
    combo = sel_el.find_element(By.CSS_SELECTOR, ".Select-input > input, .Select-input")
    seen = []
    for _ in range(80):
        combo.send_keys(Keys.ARROW_DOWN)
        sleep_fn(0.12)
        focused = driver.execute_script(
            """
            var items = document.querySelectorAll('.sell-category__item');
            var sel = arguments[0] === 0
                ? document.querySelector('.sell-category-select')
                : items[arguments[0]].querySelector('.Select');
            var f = sel ? sel.querySelector('.Select-option.is-focused') : null;
            return f ? (f.getAttribute('aria-label') || f.textContent.trim() || '') : '';
            """,
            item_index,
        )
        if focused == target_label:
            combo.send_keys(Keys.ENTER)
            sleep_fn(1.5)
            return True
        if focused:
            if focused in seen and len(seen) > 2 and focused == seen[0]:
                break
            if focused not in seen:
                seen.append(focused)
    combo.send_keys(Keys.ESCAPE)
    sleep_fn(0.3)
    return False


def find_best_option_by_arrow(
    driver,
    item_index: int,
    target_keyword: str,
    fallback_other: bool = True,
    *,
    sleep_fn,
    scroll_and_click,
) -> bool:
    """Pick the best matching option from a category React-Select."""
    stage = _category_stage_name(item_index)
    sel_el = get_category_select_el(driver, item_index)
    if sel_el is None:
        print(f"  [category][{stage}] selector not found")
        return False

    ctrl = sel_el.find_element(By.CSS_SELECTOR, ".Select-control")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", ctrl)
    sleep_fn(0.3)
    driver.execute_script("arguments[0].click()", ctrl)
    options = _wait_for_dropdown_options(driver, item_index, sleep_fn=sleep_fn)
    _log_dropdown_options(stage, target_keyword, options)

    combo = sel_el.find_element(By.CSS_SELECTOR, ".Select-input > input, .Select-input")
    combo.send_keys(target_keyword)
    options = _wait_for_dropdown_options(driver, item_index, sleep_fn=sleep_fn)
    _log_dropdown_options(stage, target_keyword, options)
    selected = _choose_option_with_priority(options, target_keyword)
    if selected and _click_option_by_signature(driver, item_index, selected, sleep_fn=sleep_fn):
        return True
    if fallback_other:
        other = _choose_option_with_priority(options, "その他")
        if other and _click_option_by_signature(driver, item_index, other, sleep_fn=sleep_fn):
            print(f"  [category][{stage}] fallback selected: その他")
            return True

    try:
        for _ in range(len(target_keyword)):
            combo.send_keys(Keys.BACK_SPACE)
        sleep_fn(0.2)
    except Exception:
        pass

    driver.execute_script("arguments[0].click()", ctrl)
    _wait_for_dropdown_options(driver, item_index, sleep_fn=sleep_fn)
    combo = sel_el.find_element(By.CSS_SELECTOR, ".Select-input > input, .Select-input")
    seen = []
    for _ in range(80):
        combo.send_keys(Keys.ARROW_DOWN)
        sleep_fn(0.12)
        focused = driver.execute_script(
            """
            var items = document.querySelectorAll('.sell-category__item');
            var sel = arguments[0] === 0
                ? document.querySelector('.sell-category-select')
                : items[arguments[0]].querySelector('.Select');
            var f = sel ? sel.querySelector('.Select-option.is-focused') : null;
            return f ? (f.getAttribute('aria-label') || f.textContent.trim() || '') : '';
            """,
            item_index,
        )
        if focused and target_keyword in focused:
            combo.send_keys(Keys.ENTER)
            sleep_fn(1.5)
            return True
        if focused:
            if focused in seen and len(seen) > 2 and focused == seen[0]:
                break
            if focused not in seen:
                seen.append(focused)
    combo.send_keys(Keys.ESCAPE)
    sleep_fn(0.3)

    if fallback_other and seen:
        print(f"  [category][{stage}] target not found, trying その他 fallback by recursive pass")
        return find_best_option_by_arrow(
            driver,
            item_index,
            "その他",
            False,
            sleep_fn=sleep_fn,
            scroll_and_click=scroll_and_click,
        )
    print(f"  [category][{stage}] selection failed target='{target_keyword}' seen={seen}")
    return False
