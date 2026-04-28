import csv
import json
import os
import unittest

from marketplace.buyma.standard_category import StandardCategory
from marketplace.common.category_classifier import classify_category
from services.category_analysis_service import (
    analyze_unresolved_categories,
    calculate_category_health,
    extract_keywords,
    generate_category_sample_csv,
    suggest_category_rules,
)


class CategoryAnalysisServiceTests(unittest.TestCase):
    def _make_runtime_dir(self, name: str) -> str:
        path = os.path.join(os.getcwd(), ".runtime", "tests", name)
        os.makedirs(path, exist_ok=True)
        return path

    def test_category_health_no_data(self):
        health = calculate_category_health(total_rows=0, unresolved_count=0)
        self.assertEqual(health["status"], "NO_DATA")

    def test_category_health_csv_input(self):
        base = self._make_runtime_dir("health_csv")
        input_csv = os.path.join(base, "sample.csv")
        with open(input_csv, "w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.writer(fp)
            writer.writerow(["row", "product_name", "brand", "category"])
            writer.writerow([1, "dress item", "A", "미분류"])
            writer.writerow([2, "shirt item", "B", "TOP_SHIRT"])
        report = analyze_unresolved_categories(logs_dir=os.path.join(base, "logs"), input_csv=input_csv)
        health = calculate_category_health(report["total_rows"], len(report["rows"]))
        self.assertEqual(health["total_rows"], 2)
        self.assertEqual(health["unresolved"], 1)

    def test_sample_csv_generation(self):
        base = self._make_runtime_dir("sample_gen")
        path = generate_category_sample_csv(logs_dir=os.path.join(base, "logs"))
        self.assertTrue(os.path.exists(path))
        with open(path, "r", encoding="utf-8-sig", newline="") as fp:
            rows = list(csv.reader(fp))
        self.assertGreaterEqual(len(rows), 31)  # header + 30

    def test_rule_suggestion_with_input_csv(self):
        base = self._make_runtime_dir("suggest_csv")
        input_csv = os.path.join(base, "sample.csv")
        with open(input_csv, "w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.writer(fp)
            writer.writerow(["row", "product_name", "brand", "category"])
            writer.writerow([1, "pleated skirt", "A", "미분류"])
            writer.writerow([2, "mini shoulder bag", "B", "미분류"])
        result = suggest_category_rules(logs_dir=os.path.join(base, "logs"), input_csv=input_csv, top_n=10)
        self.assertTrue(any("SKIRT_LONG" in line for line in result["candidates"]))
        self.assertTrue(any("BAG_SHOULDER" in line for line in result["candidates"]))

    def test_korean_header_auto_detect(self):
        base = self._make_runtime_dir("korean_header")
        input_csv = os.path.join(base, "sample_kr.csv")
        with open(input_csv, "w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.writer(fp)
            writer.writerow(["No.", "상품명", "브랜드", "카테고리"])
            writer.writerow([1, "원피스 블랙", "BRAND", "미분류"])
        report = analyze_unresolved_categories(logs_dir=os.path.join(base, "logs"), input_csv=input_csv)
        self.assertEqual(report["total_rows"], 1)
        self.assertEqual(len(report["rows"]), 1)

    def test_stopword_filtering(self):
        tokens = extract_keywords("official black dress women 정품 무료배송 cardigan")
        self.assertIn("dress", tokens)
        self.assertIn("cardigan", tokens)
        self.assertNotIn("official", tokens)
        self.assertNotIn("black", tokens)
        self.assertNotIn("women", tokens)
        self.assertNotIn("정품", tokens)

    def test_unresolved_jsonl_creation(self):
        base = self._make_runtime_dir("category_unresolved_jsonl")
        prev = os.getcwd()
        os.chdir(base)
        try:
            result = classify_category("unknown xyz qwerty", "")
            self.assertEqual(result, StandardCategory.ETC)
            jsonl_path = os.path.join("logs", "category_unresolved.jsonl")
            self.assertTrue(os.path.exists(jsonl_path))
            with open(jsonl_path, "r", encoding="utf-8") as fp:
                line = fp.readline().strip()
            payload = json.loads(line)
            self.assertIn("product_name", payload)
            self.assertIn("tokens", payload)
        finally:
            os.chdir(prev)


if __name__ == "__main__":
    unittest.main()
