import csv
import json
import os
import unittest

from marketplace.buyma.standard_category import StandardCategory
from marketplace.common.category_classifier import classify_category
from services.category_analysis_service import (
    CATEGORY_HINTS,
    analyze_unresolved_categories,
    category_health,
    calculate_category_health,
    extract_ngrams,
    extract_keywords,
    generate_category_sample_csv,
    is_valid_product_row,
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

    def test_category_health_reclassify(self):
        base = self._make_runtime_dir("health_reclassify")
        input_csv = os.path.join(base, "sample.csv")
        with open(input_csv, "w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.writer(fp)
            writer.writerow(["row", "product_name", "brand", "category"])
            writer.writerow([1, "심리스 이너프리 브라", "KINDAME", "미분류"])
            writer.writerow([2, "골반뽕 힙업 팬티", "KINDAME", "미분류"])
            writer.writerow([3, "홈웨어 파자마 세트", "", "미분류"])
        health = category_health(logs_dir=os.path.join(base, "logs"), input_csv=input_csv, reclassify=True)
        self.assertLess(health["unresolved"], 3)
        self.assertGreater(health.get("matched_by", {}).get("force_map", 0), 0)

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
        self.assertIn("official", tokens)
        self.assertIn("black", tokens)

    def test_extract_ngrams(self):
        grams = extract_ngrams(["pleated", "skirt", "mini"])
        self.assertIn("pleated", grams)
        self.assertIn("pleated skirt", grams)
        self.assertIn("pleated skirt mini", grams)

    def test_phrase_based_rule_suggestion(self):
        base = self._make_runtime_dir("phrase_suggest")
        input_csv = os.path.join(base, "phrase.csv")
        with open(input_csv, "w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.writer(fp)
            writer.writerow(["row", "product_name", "brand", "category"])
            writer.writerow([1, "pleated skirt mini", "A", "미분류"])
            writer.writerow([2, "pleated skirt long", "B", "미분류"])
            writer.writerow([3, "mini shoulder bag", "C", "미분류"])
            writer.writerow([4, "crossbody bag mini", "D", "미분류"])
            writer.writerow([5, "floral mini dress", "E", "미분류"])
            writer.writerow([6, "summer mini dress", "F", "미분류"])
        result = suggest_category_rules(logs_dir=os.path.join(base, "logs"), input_csv=input_csv, top_n=10)
        self.assertGreater(len(result["candidates"]), 0)
        self.assertTrue(any("pleated skirt" in line for line in result["candidates"]))
        self.assertTrue(any("shoulder bag" in line or "crossbody bag" in line for line in result["candidates"]))

    def test_unigram_vs_bigram(self):
        base = self._make_runtime_dir("unigram_bigram")
        input_csv = os.path.join(base, "grams.csv")
        with open(input_csv, "w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.writer(fp)
            writer.writerow(["row", "product_name", "brand", "category"])
            writer.writerow([1, "pleated skirt mini", "A", "미분류"])
            writer.writerow([2, "pleated skirt midi", "B", "미분류"])
            writer.writerow([3, "pleated skirt long", "C", "미분류"])
        result = suggest_category_rules(logs_dir=os.path.join(base, "logs"), input_csv=input_csv, top_n=10)
        top_phrases = [p for p, _c in result.get("top_phrases", [])]
        self.assertIn("pleated skirt", top_phrases)
        self.assertIn("skirt", top_phrases)

    def test_category_hints_expanded(self):
        required = {
            "mini dress",
            "onepiece",
            "blouse",
            "down jacket",
            "crossbody",
            "tote bag",
            "hat",
            "beanie",
            "sneakers",
            "denim",
            "jeans",
            "cargo pants",
        }
        self.assertTrue(required.issubset(set(CATEGORY_HINTS.keys())))

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

    def test_empty_row_excluded(self):
        base = self._make_runtime_dir("empty_row_excluded")
        input_csv = os.path.join(base, "sample.csv")
        with open(input_csv, "w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.writer(fp)
            writer.writerow(["row", "product_name", "brand", "category", "url"])
            writer.writerow([1, "", "", "미분류", ""])
            writer.writerow([2, "심리스 브라", "", "미분류", ""])
        report = analyze_unresolved_categories(logs_dir=os.path.join(base, "logs"), input_csv=input_csv)
        self.assertEqual(report["total_csv_rows"], 2)
        self.assertEqual(report["valid_product_rows"], 1)
        self.assertEqual(report["empty_rows"], 1)

    def test_value_product_name_treated_empty(self):
        self.assertFalse(is_valid_product_row({"product_name": "#VALUE!", "brand": "", "url": ""}))

    def test_category_health_counts_valid_rows(self):
        base = self._make_runtime_dir("health_valid_counts")
        input_csv = os.path.join(base, "sample.csv")
        with open(input_csv, "w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.writer(fp)
            writer.writerow(["row", "product_name", "brand", "category"])
            for i in range(1, 1001):
                if i <= 374:
                    category = "미분류" if i <= 10 else "TOP_SHIRT"
                    writer.writerow([i, f"product {i}", "brand", category])
                else:
                    writer.writerow([i, "", "", ""])
        health = category_health(logs_dir=os.path.join(base, "logs"), input_csv=input_csv)
        self.assertEqual(health["total_csv_rows"], 1000)
        self.assertEqual(health["valid_product_rows"], 374)
        self.assertEqual(health["empty_rows"], 626)
        self.assertEqual(health["unresolved"], 10)


if __name__ == "__main__":
    unittest.main()
