from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict, List

from services.category_analysis_service import (
    analyze_unresolved_categories,
    calculate_category_health,
    load_category_rows,
)
from services.category_rule_apply_service import apply_category_rules
from marketplace.common.category_classifier import normalize_product_name
from marketplace.common.category_classifier import classify_category_with_reason
from marketplace.buyma.standard_category import StandardCategory


def _status_from_rates(before_rate: float, after_rate: float) -> str:
    if after_rate <= 10.0:
        return "PASS"
    if after_rate < before_rate:
        return "IMPROVED"
    if after_rate == before_rate:
        return "NO_CHANGE"
    return "REGRESSED"


def classify_with_candidate_rules(product_name: str, brand: str, applicable_candidates: List[Dict[str, str]]) -> bool:
    clean_name = normalize_product_name(product_name)
    text = f"{clean_name} {brand}".lower()
    if not text.strip():
        return False

    candidate_patterns = [(c.get("pattern", "") or "").strip().lower() for c in applicable_candidates]
    candidate_patterns = [p for p in candidate_patterns if p]
    for pattern in candidate_patterns:
        if pattern in text:
            return True

    category, _reason = classify_category_with_reason(clean_name, brand)
    return category != StandardCategory.ETC


def _simulate_after_reclassify(
    rows: List[object],
    applicable_candidates: List[Dict[str, str]],
) -> Dict[str, object]:
    matched_by = {
        "force_map": 0,
        "fallback_rules": 0,
        "candidate_rules": 0,
        "unresolved": 0,
    }
    unresolved_after = 0
    candidate_patterns = [(c.get("pattern", "") or "").strip().lower() for c in applicable_candidates]
    candidate_patterns = [p for p in candidate_patterns if p]

    for row in rows:
        name = getattr(row, "product_name", "")
        brand = getattr(row, "brand", "")
        text = f"{normalize_product_name(name)} {brand}".lower()

        candidate_hit = any(pattern in text for pattern in candidate_patterns)
        if candidate_hit:
            matched_by["candidate_rules"] += 1

        category, reason = classify_category_with_reason(name, brand)
        if category == StandardCategory.ETC:
            unresolved_after += 1
            matched_by["unresolved"] += 1
        else:
            if reason == "force_map":
                matched_by["force_map"] += 1
            elif reason == "fallback_rules":
                matched_by["fallback_rules"] += 1
            elif candidate_hit:
                # 후보 패턴이 텍스트에 매칭된 경우 표시용으로 카운팅
                matched_by["candidate_rules"] += 0

    return {
        "unresolved_after": unresolved_after,
        "matched_by": matched_by,
    }


def run_category_tune_cycle(
    *,
    input_csv: str,
    logs_dir: str = "logs",
    dry_run: bool = True,
    classifier_path: str = os.path.join("marketplace", "common", "category_classifier.py"),
) -> Dict[str, object]:
    os.makedirs(logs_dir, exist_ok=True)
    report = analyze_unresolved_categories(logs_dir=logs_dir, input_csv=input_csv)
    total_rows = int(report.get("total_rows", 0) or 0)
    unresolved_rows = list(report.get("rows", []))
    before_unresolved = len(unresolved_rows)
    before_health = calculate_category_health(total_rows, before_unresolved)
    before_health["total_csv_rows"] = int(report.get("total_csv_rows", total_rows) or total_rows)
    before_health["valid_product_rows"] = int(report.get("valid_product_rows", total_rows) or total_rows)
    before_health["empty_rows"] = int(report.get("empty_rows", 0) or 0)
    base_rows = load_category_rows(logs_dir=logs_dir, input_csv=input_csv, include_empty=False)

    apply_result = apply_category_rules(
        input_csv=input_csv,
        classifier_path=classifier_path,
        logs_dir=logs_dir,
        dry_run=dry_run,
    )
    applicable = list(apply_result.get("applicable_candidates", []))
    sim = _simulate_after_reclassify(base_rows, applicable)
    after_unresolved = int(sim["unresolved_after"])
    after_health = calculate_category_health(total_rows, after_unresolved)
    after_health["total_csv_rows"] = before_health.get("total_csv_rows", total_rows)
    after_health["valid_product_rows"] = before_health.get("valid_product_rows", total_rows)
    after_health["empty_rows"] = before_health.get("empty_rows", 0)

    if not applicable:
        cycle_status = "NO_CHANGE"
    else:
        cycle_status = _status_from_rates(
            float(before_health["unresolved_rate"]),
            float(after_health["unresolved_rate"]),
        )

    result = {
        "ok": bool(apply_result.get("ok", True)),
        "mode": "dry-run" if dry_run else "apply",
        "before": before_health,
        "after": after_health,
        "improvement_rows": after_unresolved - before_unresolved,
        "improvement_rate_points": float(after_health["unresolved_rate"]) - float(before_health["unresolved_rate"]),
        "status": cycle_status,
        "candidates_count": int(apply_result.get("candidates_count", 0) or 0),
        "applicable_count": int(apply_result.get("applicable_count", 0) or 0),
        "skipped": list(apply_result.get("skipped", [])),
        "added_lines": list(apply_result.get("added_lines", [])),
        "backup_path": str(apply_result.get("backup_path", "") or ""),
        "matched_by": sim.get("matched_by", {}),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }

    out_path = os.path.join(logs_dir, "category_tune_cycle_result.json")
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(result, fp, ensure_ascii=False, indent=2)
    result["result_json_path"] = out_path
    return result
