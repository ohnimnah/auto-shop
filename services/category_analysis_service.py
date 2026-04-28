from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from marketplace.buyma.standard_category import StandardCategory
from marketplace.common import sheet_source as sheet_source_mod


UNRESOLVED_VALUES = {"", "미분류", "기타", "etc", "ETC", "その他"}
STOPWORDS = {
    "black", "white", "ivory", "navy", "blue", "red",
    "new", "official", "authentic", "women", "men",
    "무료배송", "정품", "공식",
}


@dataclass
class CategoryRow:
    row: int
    product_name: str
    brand: str
    category: str


@dataclass
class UnresolvedCategoryRow:
    row: int
    product_name: str
    brand: str
    current_category: str
    detected_keywords: str


def _normalize_header(text: str) -> str:
    return re.sub(r"[\s_/-]+", "", (text or "").strip().lower())


def _extract_spreadsheet_id(raw_value: str) -> str:
    value = (raw_value or "").strip()
    if not value:
        return ""
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", value)
    if match:
        return match.group(1)
    match = re.search(r"(?:^|/)d/([a-zA-Z0-9-_]+)", value)
    if match:
        return match.group(1)
    return value


def _runtime_config_path() -> str:
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return os.path.join(local_app_data, "auto_shop", "sheets_config.json")
    return os.path.join(os.path.expanduser("~"), ".auto_shop", "sheets_config.json")


def _load_runtime_sheet_config() -> Dict[str, str]:
    cfg_path = _runtime_config_path()
    if not os.path.exists(cfg_path):
        return {}
    try:
        with open(cfg_path, "r", encoding="utf-8") as fp:
            payload = json.load(fp)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def extract_keywords(text: str) -> List[str]:
    raw = re.findall(r"[a-zA-Z]{3,}|[가-힣]{2,}", (text or "").lower())
    return [token for token in raw if token not in STOPWORDS]


def _sheet_values() -> Tuple[List[List[str]], str]:
    cfg = _load_runtime_sheet_config()
    spreadsheet_id = _extract_spreadsheet_id(str(cfg.get("spreadsheet_id", "") or ""))
    sheet_name = str(cfg.get("sheet_name", "") or "").strip()
    if not spreadsheet_id or not sheet_name:
        return [], "sheet_config_missing"
    try:
        credentials_path = sheet_source_mod.get_credentials_path(os.getcwd())
        service = sheet_source_mod.get_sheets_service(credentials_path)
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!A1:ZZ5000",
        ).execute()
        return result.get("values", []), "sheet"
    except Exception:
        return [], "log_fallback"


def _header_index_map(header: List[str]) -> Dict[str, int]:
    return {
        _normalize_header(name): idx
        for idx, name in enumerate(header)
        if str(name or "").strip()
    }


def _pick(row: List[str], hmap: Dict[str, int], keys: Iterable[str]) -> str:
    for key in keys:
        idx = hmap.get(_normalize_header(key))
        if idx is not None and idx < len(row):
            value = str(row[idx] or "").strip()
            if value:
                return value
    return ""


def _rows_from_values(values: List[List[str]]) -> List[CategoryRow]:
    if not values:
        return []
    header = [str(cell or "").strip() for cell in values[0]]
    hmap = _header_index_map(header)
    rows: List[CategoryRow] = []
    for i, raw in enumerate(values[1:], start=2):
        row = [str(cell or "").strip() for cell in raw]
        if not any(row):
            continue
        product_name = _pick(row, hmap, [
            "product_name_kr", "상품명", "product_name", "title", "name",
        ])
        brand = _pick(row, hmap, ["brand", "브랜드"])
        category = _pick(row, hmap, [
            "standard_category", "무신사소분류", "musinsa_subcategory",
            "category", "카테고리",
        ])
        rows.append(CategoryRow(i, product_name, brand, category))
    return rows


def _rows_from_input_csv(input_csv: str) -> List[CategoryRow]:
    if not os.path.exists(input_csv):
        return []
    with open(input_csv, "r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.reader(fp)
        data = list(reader)
    if not data:
        return []
    header = [str(cell or "").strip() for cell in data[0]]
    hmap = _header_index_map(header)
    rows: List[CategoryRow] = []
    for i, raw in enumerate(data[1:], start=2):
        row = [str(cell or "").strip() for cell in raw]
        if not any(row):
            continue
        row_no = _pick(row, hmap, ["row", "no", "No.", "번호"]) or str(i)
        try:
            row_num = int(re.sub(r"[^0-9]", "", row_no) or i)
        except Exception:
            row_num = i
        product_name = _pick(row, hmap, [
            "product_name", "product_name_kr", "상품명", "title", "name",
        ])
        brand = _pick(row, hmap, ["brand", "브랜드"])
        category = _pick(row, hmap, [
            "category", "current_category", "카테고리", "standard_category", "무신사소분류", "musinsa_subcategory",
        ])
        rows.append(CategoryRow(row_num, product_name, brand, category))
    return rows


def _rows_from_log(logs_dir: str) -> List[CategoryRow]:
    rows: List[CategoryRow] = []
    log_path = os.path.join(logs_dir, "app.log")
    if not os.path.exists(log_path):
        return rows
    with open(log_path, "r", encoding="utf-8", errors="ignore") as fp:
        for line in fp:
            if "category_unresolved" not in line:
                continue
            m_product = re.search(r"product=([^ ]+.*?)(?: brand=|$)", line)
            m_brand = re.search(r"brand=(.*)$", line)
            product_name = (m_product.group(1).strip() if m_product else "").strip()
            brand = (m_brand.group(1).strip() if m_brand else "").strip()
            rows.append(CategoryRow(0, product_name, brand, "미분류"))
    return rows


def _to_unresolved(rows: List[CategoryRow]) -> List[UnresolvedCategoryRow]:
    unresolved: List[UnresolvedCategoryRow] = []
    for item in rows:
        cat = str(item.category or "").strip()
        if cat not in UNRESOLVED_VALUES:
            continue
        tokens = extract_keywords(f"{item.product_name} {item.brand}")
        unresolved.append(
            UnresolvedCategoryRow(
                row=item.row,
                product_name=item.product_name,
                brand=item.brand,
                current_category=cat or "미분류",
                detected_keywords=", ".join(tokens[:8]),
            )
        )
    return unresolved


def _write_unresolved_csv(unresolved_rows: List[UnresolvedCategoryRow], logs_dir: str) -> str:
    os.makedirs(logs_dir, exist_ok=True)
    csv_path = os.path.join(logs_dir, "unresolved_categories.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["row", "product_name", "brand", "current_category", "detected_keywords"])
        for item in unresolved_rows:
            writer.writerow([item.row, item.product_name, item.brand, item.current_category, item.detected_keywords])
    return csv_path


def analyze_unresolved_categories(*, logs_dir: str = "logs", input_csv: str = "") -> Dict[str, object]:
    source = "input_csv" if input_csv else "sheet"
    if input_csv:
        base_rows = _rows_from_input_csv(input_csv)
    else:
        values, source = _sheet_values()
        base_rows = _rows_from_values(values) if values else _rows_from_log(logs_dir)

    unresolved_rows = _to_unresolved(base_rows)
    keyword_counter: Counter[str] = Counter()
    for row in unresolved_rows:
        for token in [t.strip() for t in row.detected_keywords.split(",") if t.strip()]:
            keyword_counter[token] += 1

    csv_path = _write_unresolved_csv(unresolved_rows, logs_dir)
    return {
        "ok": True,
        "rows": unresolved_rows,
        "top_keywords": keyword_counter.most_common(20),
        "csv_path": csv_path,
        "source": source,
        "total_rows": len(base_rows),
    }


def calculate_category_health(total_rows: int, unresolved_count: int) -> Dict[str, object]:
    classified = max(0, total_rows - unresolved_count)
    if total_rows == 0:
        unresolved_rate = 0.0
        status = "NO_DATA"
    else:
        unresolved_rate = (unresolved_count / total_rows) * 100
        if unresolved_rate <= 10:
            status = "OK"
        elif unresolved_rate <= 20:
            status = "WARNING"
        else:
            status = "NEEDS_TUNING"
    return {
        "total_rows": total_rows,
        "classified": classified,
        "unresolved": unresolved_count,
        "unresolved_rate": unresolved_rate,
        "status": status,
    }


def category_health(*, logs_dir: str = "logs", input_csv: str = "") -> Dict[str, object]:
    report = analyze_unresolved_categories(logs_dir=logs_dir, input_csv=input_csv)
    return calculate_category_health(int(report.get("total_rows", 0) or 0), len(report.get("rows", [])))


def _keyword_counter_from_unresolved_csv(csv_path: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    if not os.path.exists(csv_path):
        return counter
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            keywords = str(row.get("detected_keywords", "") or "")
            if keywords.strip():
                tokens = [x.strip().lower() for x in keywords.split(",") if x.strip()]
            else:
                product = str(row.get("product_name", "") or "")
                brand = str(row.get("brand", "") or "")
                tokens = extract_keywords(f"{product} {brand}")
            for token in tokens:
                if token in STOPWORDS:
                    continue
                counter[token] += 1
    return counter


def suggest_category_rules(*, logs_dir: str = "logs", input_csv: str = "", top_n: int = 10) -> Dict[str, object]:
    if input_csv:
        report = analyze_unresolved_categories(logs_dir=logs_dir, input_csv=input_csv)
        csv_path = report["csv_path"]
    else:
        csv_path = os.path.join(logs_dir, "unresolved_categories.csv")
        if not os.path.exists(csv_path):
            report = analyze_unresolved_categories(logs_dir=logs_dir)
            csv_path = report["csv_path"]

    counter = _keyword_counter_from_unresolved_csv(csv_path)
    keyword_to_rule = {
        "dress": ("원피스", StandardCategory.DRESS),
        "skirt": ("스커트", StandardCategory.SKIRT_LONG),
        "cardigan": ("가디건", StandardCategory.TOP_CARDIGAN),
        "knit": ("니트", StandardCategory.TOP_KNIT),
        "shirt": ("셔츠/블라우스", StandardCategory.TOP_SHIRT),
        "coat": ("코트", StandardCategory.OUTER_COAT),
        "puffer": ("패딩", StandardCategory.OUTER_PADDING),
        "bag": ("가방", StandardCategory.BAG_SHOULDER),
        "cap": ("모자", StandardCategory.ACC_CAP),
        "belt": ("벨트", StandardCategory.ACC_BELT),
        "cargo": ("카고 팬츠", StandardCategory.PANTS_CARGO),
    }

    candidates: List[str] = []
    for keyword, _count in counter.most_common(top_n * 3):
        if keyword not in keyword_to_rule:
            continue
        label, std = keyword_to_rule[keyword]
        if keyword == "cargo":
            pattern = "cargo pants"
        elif keyword == "skirt":
            pattern = "pleated skirt"
        elif keyword == "bag":
            pattern = "shoulder bag"
        else:
            pattern = keyword
        candidates.append(f'("{label}", ["{pattern}"], StandardCategory.{std.name})')
        if len(candidates) >= top_n:
            break

    return {
        "top_tokens": counter.most_common(20),
        "candidates": candidates,
    }


def generate_category_sample_csv(*, logs_dir: str = "logs") -> str:
    os.makedirs(logs_dir, exist_ok=True)
    path = os.path.join(logs_dir, "sample_category_rows.csv")
    rows = [
        (1, "Nike short sleeve t-shirt", "NIKE", "미분류"),
        (2, "Adidas jogger pants", "ADIDAS", "미분류"),
        (3, "Pleated skirt mini", "ZARA", "미분류"),
        (4, "Wool cardigan cream", "COS", "미분류"),
        (5, "Denim jeans regular", "LEVIS", "미분류"),
        (6, "Mini shoulder bag", "GUCCI", "미분류"),
        (7, "Logo cap", "MLB", "미분류"),
        (8, "Running sneakers", "ASICS", "미분류"),
        (9, "Puffer down jacket", "MONCLER", "미분류"),
        (10, "Cotton shirt stripe", "UNIQLO", "미분류"),
        (11, "Long coat navy", "SYSTEM", "미분류"),
        (12, "Black belt leather", "HERMES", "미분류"),
        (13, "Sunglasses classic", "RAYBAN", "미분류"),
        (14, "Sports socks 3pack", "NIKE", "미분류"),
        (15, "Cargo pants wide", "CARHARTT", "미분류"),
        (16, "Dress floral", "SANDRO", "미분류"),
        (17, "Knit sweater round", "AMI", "미분류"),
        (18, "Blouse ivory", "MANGO", "미분류"),
        (19, "Crossbody bag black", "COACH", "미분류"),
        (20, "Beanie wool", "STUSSY", "미분류"),
        (21, "Unknown item abc", "BRANDX", "기타"),
        (22, "Unknown item def", "BRANDY", "미분류"),
        (23, "Jacket varsity", "SUPREME", "미분류"),
        (24, "Hoodie oversized", "FEAROFGOD", "미분류"),
        (25, "Tank top ribbed", "H&M", "미분류"),
        (26, "Slacks formal", "MASSIMODUTTI", "미분류"),
        (27, "Loafer shoes", "TODS", "미분류"),
        (28, "Sandal slide", "BIRKENSTOCK", "미분류"),
        (29, "Backpack travel", "SAMSONITE", "미분류"),
        (30, "Skirt pleated midi", "A.P.C", "미분류"),
    ]
    with open(path, "w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["row", "product_name", "brand", "category"])
        for r in rows:
            writer.writerow(r)
    return path
