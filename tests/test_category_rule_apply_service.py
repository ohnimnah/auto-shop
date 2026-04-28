import csv
import os
import unittest

from services.category_rule_apply_service import apply_category_rules


class CategoryRuleApplyServiceTests(unittest.TestCase):
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

    def test_dry_run_no_file_change(self):
        base = self._mk("rule_apply_dry")
        classifier = os.path.join(base, "category_classifier.py")
        self._write_classifier(classifier)
        csv_path = os.path.join(base, "input.csv")
        self._write_csv(csv_path, [(1, "pleated skirt", "A", "미분류")])
        with open(classifier, "r", encoding="utf-8") as fp:
            before = fp.read()
        out = apply_category_rules(input_csv=csv_path, classifier_path=classifier, logs_dir=os.path.join(base, "logs"), dry_run=True)
        with open(classifier, "r", encoding="utf-8") as fp:
            after = fp.read()
        self.assertTrue(out["ok"])
        self.assertEqual(before, after)

    def test_apply_adds_rule(self):
        base = self._mk("rule_apply_apply")
        classifier = os.path.join(base, "category_classifier.py")
        self._write_classifier(classifier)
        csv_path = os.path.join(base, "input.csv")
        self._write_csv(csv_path, [(1, "mini shoulder bag", "A", "미분류")])
        out = apply_category_rules(input_csv=csv_path, classifier_path=classifier, logs_dir=os.path.join(base, "logs"), dry_run=False)
        self.assertTrue(out["ok"])
        with open(classifier, "r", encoding="utf-8") as fp:
            content = fp.read()
        self.assertIn("BAG_SHOULDER", content)

    def test_duplicate_keyword_skipped(self):
        base = self._mk("rule_apply_dup")
        classifier = os.path.join(base, "category_classifier.py")
        self._write_classifier(classifier)
        csv_path = os.path.join(base, "input.csv")
        self._write_csv(csv_path, [(1, "existing keyword", "A", "미분류")])
        out = apply_category_rules(input_csv=csv_path, classifier_path=classifier, logs_dir=os.path.join(base, "logs"), dry_run=False)
        self.assertTrue(out["ok"])
        self.assertEqual(out["applicable_count"], 0)

    def test_unknown_standard_category_skipped(self):
        base = self._mk("rule_apply_unknown")
        classifier = os.path.join(base, "category_classifier.py")
        self._write_classifier(classifier)
        csv_path = os.path.join(base, "input.csv")
        self._write_csv(csv_path, [(1, "unknown token zz", "A", "미분류")])
        out = apply_category_rules(input_csv=csv_path, classifier_path=classifier, logs_dir=os.path.join(base, "logs"), dry_run=True)
        # token mapping 없으므로 skipped만 존재
        self.assertTrue(out["ok"])
        self.assertGreaterEqual(len(out["skipped"]), 1)

    def test_rollback_on_compile_fail(self):
        base = self._mk("rule_apply_rollback")
        classifier = os.path.join(base, "category_classifier.py")
        self._write_classifier(classifier)
        csv_path = os.path.join(base, "input.csv")
        self._write_csv(csv_path, [(1, "mini shoulder bag", "A", "미분류")])
        with open(classifier, "r", encoding="utf-8") as fp:
            before = fp.read()
        out = apply_category_rules(
            input_csv=csv_path,
            classifier_path=classifier,
            logs_dir=os.path.join(base, "logs"),
            dry_run=False,
            compile_check_fn=lambda _p: (False, "forced"),
        )
        with open(classifier, "r", encoding="utf-8") as fp:
            after = fp.read()
        self.assertFalse(out["ok"])
        self.assertTrue(out.get("rolled_back", False))
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
