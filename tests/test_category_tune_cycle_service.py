import csv
import json
import os
import unittest

from services.category_analysis_service import generate_category_sample_csv
from services.category_tune_cycle_service import (
    classify_with_candidate_rules,
    run_category_tune_cycle,
)


class CategoryTuneCycleServiceTests(unittest.TestCase):
    def _mk(self, name: str) -> str:
        p = os.path.join(os.getcwd(), ".runtime", "tests", name)
        os.makedirs(p, exist_ok=True)
        return p

    def _write_classifier(self, path: str) -> None:
        text = """from typing import List, Tuple
from marketplace.buyma.standard_category import StandardCategory

CATEGORY_FALLBACK_RULES: List[Tuple[str, List[str], StandardCategory]] = [
    ("기존", ["existing keyword"], StandardCategory.TOP_TSHIRT),
]
"""
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(text)

    def _write_csv(self, path: str, rows) -> None:
        with open(path, "w", encoding="utf-8-sig", newline="") as fp:
            w = csv.writer(fp)
            w.writerow(["row", "product_name", "brand", "category"])
            for r in rows:
                w.writerow(r)

    def test_dry_run_tune_cycle(self):
        base = self._mk("tune_cycle_dry")
        classifier = os.path.join(base, "category_classifier.py")
        self._write_classifier(classifier)
        input_csv = os.path.join(base, "input.csv")
        self._write_csv(input_csv, [(1, "pleated skirt", "A", "미분류"), (2, "shirt", "B", "미분류")])
        result = run_category_tune_cycle(
            input_csv=input_csv,
            logs_dir=os.path.join(base, "logs"),
            dry_run=True,
            classifier_path=classifier,
        )
        self.assertEqual(result["mode"], "dry-run")
        self.assertIn("before", result)
        self.assertIn("after", result)

    def test_apply_tune_cycle(self):
        base = self._mk("tune_cycle_apply")
        classifier = os.path.join(base, "category_classifier.py")
        self._write_classifier(classifier)
        input_csv = os.path.join(base, "input.csv")
        self._write_csv(input_csv, [(1, "mini shoulder bag", "A", "미분류")])
        result = run_category_tune_cycle(
            input_csv=input_csv,
            logs_dir=os.path.join(base, "logs"),
            dry_run=False,
            classifier_path=classifier,
        )
        self.assertEqual(result["mode"], "apply")
        self.assertTrue(result["ok"])

    def test_no_candidates_no_change(self):
        base = self._mk("tune_cycle_no_candidates")
        classifier = os.path.join(base, "category_classifier.py")
        self._write_classifier(classifier)
        input_csv = os.path.join(base, "input.csv")
        self._write_csv(input_csv, [(1, "zzxxq qwert", "A", "미분류")])
        result = run_category_tune_cycle(
            input_csv=input_csv,
            logs_dir=os.path.join(base, "logs"),
            dry_run=True,
            classifier_path=classifier,
        )
        self.assertEqual(result["applicable_count"], 0)
        self.assertEqual(result["status"], "NO_CHANGE")

    def test_improved_or_pass(self):
        base = self._mk("tune_cycle_improved")
        classifier = os.path.join(base, "category_classifier.py")
        self._write_classifier(classifier)
        input_csv = os.path.join(base, "input.csv")
        self._write_csv(
            input_csv,
            [
                (1, "pleated skirt mini", "A", "미분류"),
                (2, "mini shoulder bag", "B", "미분류"),
                (3, "unknown xyz", "C", "미분류"),
            ],
        )
        result = run_category_tune_cycle(
            input_csv=input_csv,
            logs_dir=os.path.join(base, "logs"),
            dry_run=True,
            classifier_path=classifier,
        )
        self.assertLess(result["after"]["unresolved"], result["before"]["unresolved"])
        self.assertIn(result["status"], {"IMPROVED", "PASS"})

    def test_result_json_created(self):
        base = self._mk("tune_cycle_json")
        classifier = os.path.join(base, "category_classifier.py")
        self._write_classifier(classifier)
        input_csv = os.path.join(base, "input.csv")
        self._write_csv(input_csv, [(1, "pleated skirt", "A", "미분류")])
        result = run_category_tune_cycle(
            input_csv=input_csv,
            logs_dir=os.path.join(base, "logs"),
            dry_run=True,
            classifier_path=classifier,
        )
        json_path = result["result_json_path"]
        self.assertTrue(os.path.exists(json_path))
        with open(json_path, "r", encoding="utf-8") as fp:
            payload = json.load(fp)
        self.assertIn("before", payload)
        self.assertIn("after", payload)

    def test_virtual_apply_in_dry_run(self):
        applied = classify_with_candidate_rules(
            "Pleated skirt mini",
            "ZARA",
            [{"pattern": "pleated skirt"}],
        )
        self.assertTrue(applied)

    def test_sample_tune_cycle_pass(self):
        base = self._mk("tune_cycle_sample_pass")
        classifier = os.path.join(base, "category_classifier.py")
        self._write_classifier(classifier)
        logs_dir = os.path.join(base, "logs")
        sample_csv = generate_category_sample_csv(logs_dir=logs_dir)
        result = run_category_tune_cycle(
            input_csv=sample_csv,
            logs_dir=logs_dir,
            dry_run=True,
            classifier_path=classifier,
        )
        self.assertIn(result["status"], {"PASS", "IMPROVED"})
        self.assertLess(result["after"]["unresolved_rate"], result["before"]["unresolved_rate"])

    def test_force_map_counted_in_after(self):
        base = self._mk("tune_cycle_force_map")
        classifier = os.path.join(base, "category_classifier.py")
        self._write_classifier(classifier)
        input_csv = os.path.join(base, "input.csv")
        self._write_csv(
            input_csv,
            [
                (1, "심리스 이너프리 브라", "KINDAME", "미분류"),
                (2, "골반뽕 힙업 팬티", "KINDAME", "미분류"),
            ],
        )
        result = run_category_tune_cycle(
            input_csv=input_csv,
            logs_dir=os.path.join(base, "logs"),
            dry_run=True,
            classifier_path=classifier,
        )
        self.assertGreater(result.get("matched_by", {}).get("force_map", 0), 0)

    def test_applicable_positive_reduces_after(self):
        base = self._mk("tune_cycle_applicable_reduces")
        classifier = os.path.join(base, "category_classifier.py")
        self._write_classifier(classifier)
        input_csv = os.path.join(base, "input.csv")
        self._write_csv(
            input_csv,
            [
                (1, "심리스 이너프리 브라", "KINDAME", "미분류"),
                (2, "홈웨어 파자마 세트", "", "미분류"),
                (3, "골반뽕 힙업 팬티", "", "미분류"),
            ],
        )
        result = run_category_tune_cycle(
            input_csv=input_csv,
            logs_dir=os.path.join(base, "logs"),
            dry_run=True,
            classifier_path=classifier,
        )
        self.assertGreater(result.get("applicable_count", 0), 0)
        self.assertLess(result["after"]["unresolved"], result["before"]["unresolved"])

    def test_tune_cycle_ignores_empty_rows(self):
        base = self._mk("tune_cycle_ignore_empty")
        classifier = os.path.join(base, "category_classifier.py")
        self._write_classifier(classifier)
        input_csv = os.path.join(base, "input.csv")
        self._write_csv(
            input_csv,
            [
                (1, "", "", ""),
                (2, "#VALUE!", "", "미분류"),
                (3, "심리스 브라", "KINDAME", "미분류"),
            ],
        )
        result = run_category_tune_cycle(
            input_csv=input_csv,
            logs_dir=os.path.join(base, "logs"),
            dry_run=True,
            classifier_path=classifier,
        )
        self.assertEqual(result["before"]["valid_product_rows"], 1)
        self.assertEqual(result["before"]["empty_rows"], 2)


if __name__ == "__main__":
    unittest.main()
