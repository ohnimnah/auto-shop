"""BUYMA category and gender inference helpers."""

from __future__ import annotations

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import sys
from typing import Callable, Dict, List, Tuple
from marketplace.buyma.standard_category import (
    StandardCategory,
    explain_standard_category_mapping,
    map_standard_to_buyma_middle_and_subcategory,
    resolve_standard_category,
    validate_buyma_category_path,
)
import standard_category_map as standard_category_map_mod


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

    standard_category, combined_text = resolve_standard_category(
        sheet_cat1,
        sheet_cat2,
        sheet_cat3,
        source_product_name,
    )
    is_mens_category = "メンズ" in (cat1 or "")
    # Prefer table-based mapping layer first; keep existing semantic mapper as fallback.
    mapped_parent, mapped_cat2, mapped_cat3 = standard_category_map_mod.resolve_standard_category_buyma_target(
        standard_category,
        is_mens=is_mens_category,
        combined_text=combined_text,
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

    corrected_cat2 = category_corrector(cat2, source_product_name, musinsa_category_text)
    fallback_cat1, fallback_cat2, fallback_cat3 = infer_buyma_category(product_name_kr, product_name_en, brand)
    corrected_fallback_cat2 = category_corrector(
        fallback_cat2,
        source_product_name,
        musinsa_category_text,
    )
    final_path_valid = validate_buyma_category_path(cat1, corrected_cat2, cat3)
    mapping_diag = explain_standard_category_mapping(standard_category, is_mens=is_mens_category)

    _safe_log(f"  [category][semantic] musinsa={sheet_cat1} / {sheet_cat2} / {sheet_cat3}")
    _safe_log(f"  [category][semantic] product_name={source_product_name}")
    _safe_log(f"  [category][semantic] combined_text={combined_text}")
    _safe_log(f"  [category][semantic] standard_category={standard_category.value}")
    _safe_log(f"  [category][semantic] mapped_buyma={cat1} > {corrected_cat2} > {cat3}")
    _safe_log(f"  [category][semantic] spec_buyma={mapping_diag.get('buyma_parent')} > {mapping_diag.get('buyma_middle')} > {mapping_diag.get('buyma_child')}")
    _safe_log(f"  [category][semantic] validator_passed={final_path_valid}")
    _safe_log(f"  [category][semantic] mapping_table_used={mapping_table_used}")
    _safe_log(f"  [category][semantic] legacy_used={legacy_used}")
    _safe_log(f"  [category][semantic] fallback_used={semantic_fallback_used}")

    return {
        "sheet_cat1": sheet_cat1,
        "sheet_cat2": sheet_cat2,
        "sheet_cat3": sheet_cat3,
        "cat1": cat1,
        "cat2": corrected_cat2,
        "cat3": cat3,
        "cat_source": cat_source,
        "musinsa_category_text": musinsa_category_text,
        "source_product_name": source_product_name,
        "combined_text": combined_text,
        "standard_category": standard_category.value,
        "mapping_table_used": mapping_table_used,
        "legacy_used": legacy_used,
        "semantic_fallback_used": semantic_fallback_used,
        "category_path_valid": final_path_valid,
        "mapping_validator_passed": mapping_valid,
        "fallback_cat1": fallback_cat1,
        "fallback_cat2": corrected_fallback_cat2,
        "fallback_cat3": fallback_cat3,
    }


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
        diag["failure_stage"] = "parent"
        diag["final_result"] = "failed"
        return diag

    diag["actual_selected_parent_category"] = cat1
    print(f"  ✓ 대카테: {cat1}")
    if not cat2 or not find_best_option_by_arrow(driver, 1, cat2):
        print(f"  △ 중카테 '{cat2}' 미발견, その他도 없음")
        diag["failure_stage"] = "middle"
        diag["final_result"] = "failed"
        return diag

    sel_val = driver.execute_script(
        """
        var items = document.querySelectorAll('.sell-category__item');
        if (items.length < 2) return '';
        var v = items[1].querySelector('.Select-value-label');
        return v ? v.textContent.trim() : '';
        """
    )
    diag["actual_selected_middle_category"] = sel_val or cat2
    if "その他" in sel_val and sel_val != cat2:
        print(f"  ✓ 중카테: {cat2} -> その他 (기타)")
        diag["failure_stage"] = "middle_other"
        diag["final_result"] = "other"
    else:
        print(f"  ✓ 중카테: {sel_val or cat2}")

    if not cat3:
        diag["category_selection_success"] = True
        if not diag["final_result"]:
            diag["final_result"] = "success"
        return diag

    items_count = len(driver.find_elements(By.CSS_SELECTOR, ".sell-category__item"))
    if items_count < 3:
        diag["category_selection_success"] = True
        if not diag["final_result"]:
            diag["final_result"] = "success"
        return diag

    if find_best_option_by_arrow(driver, 2, cat3):
        sel_val3 = driver.execute_script(
            """
            var items = document.querySelectorAll('.sell-category__item');
            if (items.length < 3) return '';
            var v = items[2].querySelector('.Select-value-label');
            return v ? v.textContent.trim() : '';
            """
        )
        diag["actual_selected_child_category"] = sel_val3 or cat3
        if "その他" in (sel_val3 or "") and sel_val3 != cat3:
            print(f"  ✓ 소카테: {cat3} -> その他 (기타)")
            if not diag["failure_stage"]:
                diag["failure_stage"] = "child_other"
            diag["final_result"] = "other"
        else:
            print(f"  ✓ 소카테: {sel_val3 or cat3}")
    else:
        print(f"  △ 소카테 '{cat3}' 미발견, その他도 없음")
        diag["failure_stage"] = "child"
        diag["final_result"] = "failed"
        return diag

    diag["category_selection_success"] = True
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
    sel_el = get_category_select_el(driver, item_index)
    if sel_el is None:
        return False

    ctrl = sel_el.find_element(By.CSS_SELECTOR, ".Select-control")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", ctrl)
    sleep_fn(0.3)
    driver.execute_script("arguments[0].click()", ctrl)
    sleep_fn(0.6)

    combo = sel_el.find_element(By.CSS_SELECTOR, ".Select-input > input, .Select-input")
    combo.send_keys(target_keyword)
    sleep_fn(0.8)

    try:
        options = driver.find_elements(By.CSS_SELECTOR, ".Select-menu-outer .Select-option")
        exact = next((o for o in options if o.text.strip() == target_keyword), None)
        partial = next((o for o in options if target_keyword in o.text), None)
        chosen = exact or partial
        if chosen:
            scroll_and_click(driver, chosen)
            sleep_fn(1.5)
            return True
        if fallback_other:
            other = next((o for o in options if "その他" in o.text), None)
            if other:
                scroll_and_click(driver, other)
                sleep_fn(1.5)
                return True
    except Exception:
        pass

    try:
        for _ in range(len(target_keyword)):
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
        return find_best_option_by_arrow(
            driver,
            item_index,
            "その他",
            False,
            sleep_fn=sleep_fn,
            scroll_and_click=scroll_and_click,
        )
    return False
