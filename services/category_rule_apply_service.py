from __future__ import annotations

import os
import re
import shutil
import subprocess
from datetime import datetime
from typing import Dict, List

from marketplace.buyma.standard_category import StandardCategory
from services.category_analysis_service import suggest_category_rule_candidates


def _extract_rules_block(text: str) -> tuple[int, int] | tuple[None, None]:
    m = re.search(r"CATEGORY_FALLBACK_RULES\s*:\s*List\[Tuple\[str,\s*List\[str\],\s*StandardCategory\]\]\s*=\s*\[", text)
    if not m:
        return None, None
    start = m.end() - 1  # '[' 위치
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return start, i
    return None, None


def _existing_keywords(text: str) -> set[str]:
    kws: set[str] = set()
    for m in re.finditer(r'\[\s*([^\]]*?)\s*\]\s*,\s*StandardCategory\.[A-Z_]+', text, re.DOTALL):
        inner = m.group(1)
        for q in re.finditer(r'"([^"]+)"', inner):
            kws.add(q.group(1).strip().lower())
    return kws


def _compile_check(file_path: str) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["python", "-m", "py_compile", file_path],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            return True, ""
        return False, (proc.stderr or proc.stdout or "py_compile failed").strip()
    except Exception as exc:
        return False, str(exc)


def apply_category_rules(
    *,
    input_csv: str,
    classifier_path: str = os.path.join("marketplace", "common", "category_classifier.py"),
    logs_dir: str = "logs",
    dry_run: bool = True,
    compile_check_fn=None,
    top_token_n: int = 200,
) -> Dict[str, object]:
    suggest = suggest_category_rule_candidates(logs_dir=logs_dir, input_csv=input_csv, top_token_n=top_token_n)
    candidates: List[Dict[str, str]] = list(suggest.get("candidates", []))
    skipped: List[Dict[str, str]] = list(suggest.get("skipped", []))

    if not os.path.exists(classifier_path):
        return {
            "ok": False,
            "reason": f"classifier_not_found: {classifier_path}",
            "mode": "dry-run" if dry_run else "apply",
            "candidates_count": len(candidates),
            "applicable_count": 0,
            "skipped": skipped,
            "added_lines": [],
        }

    with open(classifier_path, "r", encoding="utf-8") as fp:
        original = fp.read()

    block_start, block_end = _extract_rules_block(original)
    if block_start is None or block_end is None:
        return {
            "ok": False,
            "reason": "CATEGORY_FALLBACK_RULES block not found",
            "mode": "dry-run" if dry_run else "apply",
            "candidates_count": len(candidates),
            "applicable_count": 0,
            "skipped": skipped,
            "added_lines": [],
        }

    existing_kws = _existing_keywords(original[block_start:block_end + 1])
    applicable: List[Dict[str, str]] = []
    for c in candidates:
        std_name = c.get("std_name", "")
        if not hasattr(StandardCategory, std_name):
            skipped.append({"token": c.get("token", ""), "reason": f"unknown StandardCategory.{std_name}"})
            continue
        pattern = (c.get("pattern", "") or "").strip().lower()
        if pattern in existing_kws:
            skipped.append({"token": c.get("token", ""), "reason": f"duplicate keyword '{pattern}'"})
            continue
        applicable.append(c)

    added_lines = [f'    {c["line"]},' for c in applicable]
    if dry_run:
        return {
            "ok": True,
            "mode": "dry-run",
            "candidates_count": len(candidates),
            "applicable_count": len(applicable),
            "skipped": skipped,
            "added_lines": added_lines,
            "applicable_candidates": applicable,
            "backup_path": "",
        }

    if not applicable:
        return {
            "ok": True,
            "mode": "apply",
            "candidates_count": len(candidates),
            "applicable_count": 0,
            "skipped": skipped,
            "added_lines": [],
            "applicable_candidates": [],
            "backup_path": "",
            "applied": False,
        }

    backup_path = f"{classifier_path}.bak.{datetime.now():%Y%m%d_%H%M%S}"
    os.makedirs(os.path.dirname(classifier_path), exist_ok=True)
    shutil.copyfile(classifier_path, backup_path)

    rules_block = original[block_start:block_end + 1]
    insertion = "\n" + "\n".join(added_lines) + "\n"
    new_block = rules_block[:-1] + insertion + "]"
    updated = original[:block_start] + new_block + original[block_end + 1:]

    with open(classifier_path, "w", encoding="utf-8") as fp:
        fp.write(updated)

    checker = compile_check_fn or _compile_check
    ok, err = checker(classifier_path)
    if not ok:
        shutil.copyfile(backup_path, classifier_path)
        return {
            "ok": False,
            "mode": "apply",
            "reason": f"py_compile_failed: {err}",
            "candidates_count": len(candidates),
            "applicable_count": len(applicable),
            "skipped": skipped,
            "added_lines": added_lines,
            "applicable_candidates": applicable,
            "backup_path": backup_path,
            "rolled_back": True,
        }

    return {
        "ok": True,
        "mode": "apply",
        "candidates_count": len(candidates),
        "applicable_count": len(applicable),
        "skipped": skipped,
        "added_lines": added_lines,
        "applicable_candidates": applicable,
        "backup_path": backup_path,
        "applied": True,
    }
