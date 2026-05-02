import json
import tempfile
import unittest
from contextlib import contextmanager
import shutil
import os
import uuid

from services.dashboard_data_service import DashboardDataService
from services.pipeline_service import LauncherPipelineService
from state.app_state import AppState, LogEvent


class FakeProcessManager:
    def __init__(self):
        self.running = False
        self.team_running = set()

    def is_running(self):
        return self.running

    def is_team_running(self, team_key):
        return team_key in self.team_running


class FakeSystemChecker:
    def get_available_credentials_path(self):
        return ""

    def load_sheet_config(self):
        return {}

    def normalize_spreadsheet_id(self, value):
        return value

    def is_valid_spreadsheet_id(self, value):
        return False


class FakeSheetSystemChecker(FakeSystemChecker):
    def get_available_credentials_path(self):
        return "/tmp/credentials.json"

    def load_sheet_config(self):
        return {"spreadsheet_id": "a" * 30, "sheet_name": "collection"}

    def is_valid_spreadsheet_id(self, value):
        return True


class DashboardDataServiceTests(unittest.TestCase):
    @contextmanager
    def _workspace_tempdir(self):
        os.makedirs("logs", exist_ok=True)
        path = os.path.join("logs", f"test_dashboard_data_{uuid.uuid4().hex}")
        os.makedirs(path, exist_ok=True)
        try:
            yield path
        finally:
            shutil.rmtree(path, ignore_errors=True)

    def _service(self, temp_dir, state=None, manager=None):
        return DashboardDataService(
            data_dir=temp_dir,
            script_dir=temp_dir,
            state=state or AppState(),
            process_manager=manager or FakeProcessManager(),
            system_checker=FakeSystemChecker(),
            pipeline_service=LauncherPipelineService(),
        )

    def test_load_products_from_local_json(self):
        with self._workspace_tempdir() as temp_dir:
            with open(f"{temp_dir}/products.json", "w", encoding="utf-8") as file:
                json.dump(
                    {
                        "products": [
                            {"상품명": "A", "브랜드": "Brand", "상태": "출품 완료", "가격": "1000"},
                            {"상품명": "B", "브랜드": "Brand", "상태": "업로드 실패", "가격": "2000"},
                        ]
                    },
                    file,
                    ensure_ascii=False,
                )
            rows = self._service(temp_dir).load_products()

            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0].name, "A")
            self.assertEqual(rows[1].action, "재실행 / 열기")

    def test_load_products_reports_local_json_source(self):
        with self._workspace_tempdir() as temp_dir:
            with open(f"{temp_dir}/products.json", "w", encoding="utf-8") as file:
                json.dump({"products": [{"상품명": "A", "상태": "대기"}]}, file, ensure_ascii=False)

            rows, source, detail = self._service(temp_dir).load_products_with_source()

            self.assertEqual(len(rows), 1)
            self.assertEqual(source, "로컬 JSON 사용 중")
            self.assertIn("로컬", detail)

    def test_load_products_reports_no_data_source(self):
        with self._workspace_tempdir() as temp_dir:
            rows, source, detail = self._service(temp_dir).load_products_with_source()

            self.assertEqual(rows, [])
            self.assertEqual(source, "데이터 없음")
            self.assertIn("Google Sheet", detail)

    def test_load_products_reports_empty_google_sheet_source(self):
        with self._workspace_tempdir() as temp_dir:
            service = DashboardDataService(
                data_dir=temp_dir,
                script_dir=temp_dir,
                state=AppState(),
                process_manager=FakeProcessManager(),
                system_checker=FakeSheetSystemChecker(),
                pipeline_service=LauncherPipelineService(),
            )

            rows, source, detail = service.load_products_with_source()

            self.assertEqual(rows, [])
            self.assertEqual(source, "Google Sheet 사용 중")
            self.assertIn("상품 행", detail)

    def test_metrics_use_products_and_runtime(self):
        with self._workspace_tempdir() as temp_dir:
            manager = FakeProcessManager()
            manager.running = True
            manager.team_running.add("assets")
            service = self._service(temp_dir, manager=manager)
            rows = [
                service._product_from_mapping({"상태": "대기", "상품명": "A"}, "1", "local"),
                service._product_from_mapping({"상태": "출품 완료", "상품명": "B"}, "2", "local"),
                service._product_from_mapping({"상태": "업로드 실패", "상품명": "C"}, "3", "local"),
            ]

            metrics = service.get_real_metrics(rows)

            self.assertEqual(metrics.total, 3)
            self.assertEqual(metrics.running, 2)
            self.assertEqual(metrics.waiting, 1)
            self.assertEqual(metrics.done, 1)
            self.assertEqual(metrics.error, 1)

    def test_upload_recent_rows_include_only_uploaded_products(self):
        with self._workspace_tempdir() as temp_dir:
            state = AppState()
            service = self._service(temp_dir, state=state)
            rows = [
                service._product_from_mapping({"상태": "이미지 저장 완료", "상품명": "Image"}, "1", "local"),
                service._product_from_mapping({"상태": "썸네일완료", "상품명": "Thumb"}, "2", "local"),
                service._product_from_mapping({"상태": "보류", "상품명": "Hold"}, "3", "local"),
                service._product_from_mapping({"상태": "출품완료", "상품명": "Uploaded A"}, "4", "local"),
                service._product_from_mapping({"상태": "업로드 완료", "상품명": "Uploaded B"}, "5", "local"),
            ]
            state.set_product_rows(rows)

            overview = service.get_upload_overview()

            self.assertEqual([row.name for row in overview["recent_rows"]], ["Uploaded B", "Uploaded A"])

    def test_scout_recent_rows_include_only_collected_products(self):
        with self._workspace_tempdir() as temp_dir:
            state = AppState()
            service = self._service(temp_dir, state=state)
            rows = [
                service._product_from_mapping({"상태": "수집완료", "상품명": "Collected A"}, "1", "local"),
                service._product_from_mapping({"상태": "이미지 저장 완료", "상품명": "Image"}, "2", "local"),
                service._product_from_mapping({"상태": "썸네일완료", "상품명": "Thumb"}, "3", "local"),
                service._product_from_mapping({"상태": "보류", "상품명": "Hold"}, "4", "local"),
                service._product_from_mapping({"상태": "출품완료", "상품명": "Uploaded"}, "5", "local"),
                service._product_from_mapping({"상태": "정찰 완료", "상품명": "Collected B"}, "6", "local"),
            ]
            state.set_product_rows(rows)

            overview = service.get_scout_overview()

            self.assertEqual([row.name for row in overview["recent_rows"]], ["Collected B", "Collected A"])

    def test_log_event_updates_state_and_pipeline(self):
        with self._workspace_tempdir() as temp_dir:
            state = AppState()
            service = self._service(temp_dir, state=state)

            service.update_state_from_log(LogEvent(level="INFO", category="업로드", message="상품 업로드 완료\n"))

            self.assertEqual(state.pipeline_status["sales"], "진행중")
            self.assertEqual(state.today_success, 1)
            self.assertGreaterEqual(len(state.pipeline_steps), 1)


if __name__ == "__main__":
    unittest.main()
