"""Real dashboard data loading and runtime aggregation."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from functools import lru_cache
from typing import Iterable

from config.config_service import load_config as load_profile_config
from core.process_manager import ProcessManager
from services.pipeline_service import LauncherPipelineService
from services.system_checker import SystemChecker
from state.app_state import AppState, AppStateChange, DashboardMetrics, LogEvent, PipelineStep, ProductRow


DONE_WORDS = ("완료", "성공", "출품", "업로드 완료", "정상")
ERROR_WORDS = ("실패", "오류", "error", "보류", "미칭", "exception")
WAITING_WORDS = ("대기", "준비", "미처리", "pending", "")
SHEET_COL_NAME_KR = 4  # E열 (0-based)
SHEET_COL_PRICE_BUYMA = 12  # M열 (0-based)
SHEET_COL_MUSINSA_SUBCATEGORY = 24  # Y열 (0-based, 무신사 소분류)
SHEET_COL_CATEGORY_BUYMA = 11  # L열 (0-based, 보조)


@lru_cache(maxsize=16)
def _read_json_payload(path: str, mtime: float) -> object:
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


@lru_cache(maxsize=32)
def _read_log_payloads(path: str, mtime: float) -> tuple[dict, ...]:
    payloads: list[dict] = []
    with open(path, "r", encoding="utf-8") as file:
        for raw_line in file:
            try:
                payload = json.loads(raw_line)
            except Exception:
                continue
            if isinstance(payload, dict):
                payloads.append(payload)
    return tuple(payloads)


class DashboardDataService:
    """Build KPI, pipeline, and product rows from real runtime/data sources."""

    def __init__(
        self,
        *,
        data_dir: str,
        script_dir: str,
        state: AppState,
        process_manager: ProcessManager,
        system_checker: SystemChecker,
        pipeline_service: LauncherPipelineService,
    ) -> None:
        self.data_dir = data_dir
        self.script_dir = script_dir
        self.state = state
        self.process_manager = process_manager
        self.system_checker = system_checker
        self.pipeline_service = pipeline_service

    def refresh(self) -> None:
        self.clear_caches()
        products, source_label, source_detail = self.load_products_with_source()
        self.state.set_product_rows(products)
        self.state.set_metrics(self.get_real_metrics(products))
        self.state.set_pipeline_steps(self.build_pipeline_from_runtime(products))
        self.state.set_data_source_status(source_label, datetime.now().strftime("%H:%M:%S"), source_detail)

    def clear_caches(self) -> None:
        _read_json_payload.cache_clear()
        _read_log_payloads.cache_clear()

    def get_scout_overview(self) -> dict:
        products = self.state.product_rows
        valid_products = [row for row in products if self._is_valid_product_row(row)]
        collected = sum(1 for row in valid_products if self._matches_words(row.state, ("수집", "정찰", "완료", "성공")))
        failed = sum(1 for row in valid_products if self._matches_words(row.state, ("수집 실패", "정찰 실패", "실패", "오류")))
        running = 1 if self.state.current_action in {"run", "collect-listings", "watch"} else 0
        categories = self._group_count(valid_products, lambda row: row.category or "미분류")
        unresolved = sum(
            1
            for row in valid_products
            if str((row.category or "")).strip().lower() in {"", "미분류", "기타", "etc", "その他"}
        )
        unresolved_ratio = unresolved / max(1, len(valid_products))
        if unresolved_ratio <= 0.10:
            unresolved_status = "OK"
        elif unresolved_ratio <= 0.20:
            unresolved_status = "WARNING"
        else:
            unresolved_status = "NEEDS_TUNING"
        return {
            "metrics": [
                ("수집 대상", len(valid_products), "유효 상품 행 기준"),
                ("수집 성공", collected, "수집 완료 또는 정찰 완료"),
                ("수집 실패", failed, "실패 / 오류 상태"),
                ("진행 중", running, "현재 정찰 프로세스"),
            ],
            "recent_rows": valid_products[:10],
            "category_rows": categories[:6],
            "category_rows_all": categories,
            "ratio": min(1.0, collected / max(1, len(valid_products))),
            "unresolved_count": unresolved,
            "unresolved_ratio": unresolved_ratio,
            "category_tuning_required": unresolved_ratio > 0.10,
            "unresolved_status": unresolved_status,
        }

    def get_image_overview(self) -> dict:
        products = self.state.product_rows
        downloaded = sum(1 for row in products if self._matches_words(row.state, ("이미지", "저장", "다운로드")))
        thumbs = sum(1 for row in products if self._matches_words(row.state, ("썸네일", "디자인")))
        failures = sum(1 for row in products if self._matches_words(row.state, ("이미지 실패", "썸네일 실패", "실패", "오류")))
        missing = max(0, len(products) - downloaded)
        return {
            "metrics": [
                ("이미지 다운로드", downloaded, "이미지 저장 완료 기준"),
                ("썸네일 생성", thumbs, "썸네일 생성 완료 기준"),
                ("누락 이미지", missing, "이미지 저장 전 상품"),
                ("실패 이미지", failures, "이미지 / 썸네일 실패"),
            ],
            "preview_rows": products[:8],
            "failed_rows": [row for row in products if self._is_error(row.state)][:8],
            "ratio": min(1.0, downloaded / max(1, len(products))),
        }

    def get_upload_overview(self) -> dict:
        products = self.state.product_rows
        uploaded = sum(1 for row in products if self._matches_words(row.state, ("출품", "업로드 완료", "출품완료", "완료")))
        failed = sum(1 for row in products if self._matches_words(row.state, ("업로드 실패", "출품 실패", "오류", "보류")))
        waiting = sum(1 for row in products if self._matches_words(row.state, ("업로드 대기", "대기", "준비")))
        other_ratio = sum(1 for row in products if "기타" in row.category or "その他" in row.category) / max(1, len(products))
        reasons = self._group_count([row for row in products if self._is_error(row.state)], lambda row: row.state or "오류")
        recovery_stats = self._load_upload_recovery_stats()
        return {
            "metrics": [
                ("업로드 시도", uploaded + failed, "완료 + 실패 기준"),
                ("업로드 성공", uploaded, "출품 완료 기준"),
                ("업로드 실패", failed, "업로드 실패 / 오류"),
                ("보류 중", waiting, "업로드 대기 상태"),
            ],
            "success_ratio": uploaded / max(1, uploaded + failed),
            "recent_rows": products[:10],
            "failure_reasons": reasons[:6],
            "category_failures": failed,
            "other_ratio": other_ratio,
            "recovery_success_ratio": recovery_stats["success_ratio"],
            "recovery_counts": recovery_stats["counts"],
        }

    def get_automation_overview(self) -> dict:
        watch_running = self.state.current_action == "watch"
        team_watch_running_count = sum(1 for enabled in self.state.team_watch_enabled.values() if enabled)
        team_cards = [
            ("정찰", self.state.pipeline_status.get("scout", "대기"), self.state.current_action in {"watch", "run"}),
            ("이미지", self.state.pipeline_status.get("assets", "대기"), self.state.team_watch_enabled.get("assets", False)),
            ("썸네일", self.state.pipeline_status.get("design", "대기"), self.state.team_watch_enabled.get("design", False)),
            ("업로드", self.state.pipeline_status.get("sales", "대기"), self.state.team_watch_enabled.get("sales", False)),
        ]
        team_failures = sum(self.state.team_watch_failures.values())
        return {
            "metrics": [
                ("Watch 상태", 1 if watch_running else 0, self.state.status_text),
                ("자동 새로고침", 1 if self.process_manager.is_running() else 0, "프로세스 실행 기준"),
                ("팀 감시 활성", team_watch_running_count, "assets / design / sales"),
                ("실패 누적", team_failures, "team watch 누적 실패"),
            ],
            "team_cards": team_cards,
            "failures": dict(self.state.team_watch_failures),
            "retry_count": team_failures,
            "watch_running": watch_running,
            "team_watch_running_count": team_watch_running_count,
            "recent_logs": self._load_recent_log_lines(limit=30, categories={"automation", "process", "scout", "assets", "design", "buyma", "sales"}),
        }

    def get_settings_overview(self) -> dict:
        config = self.system_checker.load_sheet_config()
        profile_name = os.path.basename(self.data_dir.rstrip(os.sep))
        if profile_name == ".auto_shop":
            profile_name = "default"
        profile_config = load_profile_config(profile_name)
        tabs_cfg = ((profile_config.get("spreadsheet") or {}).get("tabs") or {})
        return {
            "user_name": profile_name,
            "profile_name": profile_name,
            "run_mode": self.state.current_action or "idle",
            "log_level": "INFO",
            "sheet_enabled": bool(self._has_sheet_source()),
            "spreadsheet_id": self.system_checker.normalize_spreadsheet_id(config.get("spreadsheet_id", "")),
            "sheet_name": str((tabs_cfg.get("product_input") or config.get("sheet_name") or "")).strip(),
            "log_sheet_name": str((tabs_cfg.get("log") or config.get("log_sheet_name") or "log")).strip(),
            "images_dir": self._safe_path(config.get("images_dir") or ""),
            "log_dir": self._safe_path(os.path.join(self.data_dir, "logs")),
            "buyma_email": self.system_checker.load_buyma_email(),
            "buyma_credentials_path": self._safe_path(self.system_checker.get_buyma_credentials_target_path()),
            "max_concurrency": "1",
            "retry_limit": "3",
            "timeout_seconds": "120",
        }

    def update_state_from_log(self, event: LogEvent) -> None:
        stage_key = self._stage_from_event(event)
        if stage_key:
            self.state.set_stage_status(stage_key, "진행중")
        message = event.message.lower()
        if self._looks_like_product_success(event):
            self.state.record_process_done(True)
        elif self._looks_like_product_failure(event):
            self.state.record_process_done(False)
        self.state.set_metrics(self.get_real_metrics(self.state.product_rows))
        self.state.set_pipeline_steps(self.build_pipeline_from_runtime(self.state.product_rows))

    def update_state_from_change(self, change: AppStateChange) -> None:
        if not (
            change.key in {"current_action", "today_processed", "today_success", "today_fail"}
            or change.key.startswith("pipeline_status.")
            or change.key.startswith("team_watch_enabled.")
        ):
            return
        self.state.set_metrics(self.get_real_metrics(self.state.product_rows))
        self.state.set_pipeline_steps(self.build_pipeline_from_runtime(self.state.product_rows))

    def get_real_metrics(self, products: list[ProductRow] | None = None) -> DashboardMetrics:
        products = products if products is not None else self.load_products()
        valid_products = [row for row in products if self._is_valid_product_row(row)]
        done_from_products = sum(1 for row in valid_products if self._is_done(row.state))
        error_from_products = sum(1 for row in valid_products if self._is_error(row.state))
        waiting = max(0, len(valid_products) - done_from_products - error_from_products)
        return DashboardMetrics(
            total=len(valid_products),
            running=self._running_count(),
            waiting=waiting,
            done=done_from_products,
            error=error_from_products,
        )

    def build_pipeline_from_runtime(self, products: list[ProductRow] | None = None) -> list[PipelineStep]:
        products = products if products is not None else self.load_products()
        valid_products = [row for row in products if self._is_valid_product_row(row)]
        total = max(1, len(valid_products))
        stage_specs = [
            ("scout", "정찰", "blue", ("정찰", "수집", "상품")),
            ("assets", "이미지 저장", "green", ("이미지", "저장")),
            ("design", "썸네일 생성", "purple", ("썸네일", "디자인")),
            ("sales", "업로드", "orange", ("업로드", "출품", "buyma")),
            ("done", "완료", "green", DONE_WORDS),
            ("error", "오류 / 보류", "red", ERROR_WORDS),
        ]
        steps: list[PipelineStep] = []
        for key, title, color_key, words in stage_specs:
            count = self._count_rows_matching(valid_products, words)
            if key in self.state.pipeline_status and self.state.pipeline_status.get(key) in {"진행중", "감시중"}:
                count = max(count, 1)
            ratio = min(1.0, count / total)
            steps.append(PipelineStep(key, title, f"{count} / {len(valid_products)}", ratio, color_key))
        return steps

    def load_products(self) -> list[ProductRow]:
        rows, _source, _detail = self.load_products_with_source()
        return rows

    def load_products_with_source(self) -> tuple[list[ProductRow], str, str]:
        rows = self._load_products_from_sheet()
        if rows:
            return rows, "Google Sheet 사용 중", "Google Sheet에서 상품 목록을 동기화했습니다."
        if self._has_sheet_source():
            return rows, "Google Sheet 사용 중", "시트 연결은 되었지만 표시할 상품 행이 없습니다."
        rows = self._load_products_from_local_json()
        if rows:
            return rows, "로컬 JSON 사용 중", "로컬 상품 JSON에서 상품 목록을 불러왔습니다."
        if self._has_local_json_source():
            return rows, "로컬 JSON 사용 중", "로컬 JSON 파일은 있지만 표시할 상품이 없습니다."
        return [], "데이터 없음", "Google Sheet 또는 로컬 상품 JSON을 연결하면 상품이 표시됩니다."

    def _load_products_from_sheet(self) -> list[ProductRow]:
        credentials_path = self.system_checker.get_available_credentials_path()
        config = self.system_checker.load_sheet_config()
        spreadsheet_id = self.system_checker.normalize_spreadsheet_id(config.get("spreadsheet_id", ""))
        sheet_name = (config.get("sheet_name") or "").strip()
        if not credentials_path or not self.system_checker.is_valid_spreadsheet_id(spreadsheet_id) or not sheet_name:
            return []
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build

            creds = Credentials.from_service_account_file(
                credentials_path,
                scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
            )
            service = build("sheets", "v4", credentials=creds)
            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=f"'{sheet_name}'!A1:Z5000",
            ).execute()
            values = result.get("values", [])
            return self._rows_from_sheet_values(values, sheet_name)
        except Exception:
            return []

    def _has_sheet_source(self) -> bool:
        config = self.system_checker.load_sheet_config()
        spreadsheet_id = self.system_checker.normalize_spreadsheet_id(config.get("spreadsheet_id", ""))
        sheet_name = (config.get("sheet_name") or "").strip()
        return bool(
            self.system_checker.get_available_credentials_path()
            and self.system_checker.is_valid_spreadsheet_id(spreadsheet_id)
            and sheet_name
        )

    def _load_products_from_local_json(self) -> list[ProductRow]:
        candidates = [
            os.path.join(self.data_dir, "products.json"),
            os.path.join(self.data_dir, "product_rows.json"),
            os.path.join(self.data_dir, "crawl_results.json"),
            os.path.join(self.script_dir, "products.json"),
            os.path.join(self.script_dir, "crawl_results.json"),
            os.path.join(self.script_dir, "musinsa_products.json"),
        ]
        for path in candidates:
            rows = self._load_json_rows(path)
            if rows:
                return rows
        return []

    def _has_local_json_source(self) -> bool:
        candidates = [
            os.path.join(self.data_dir, "products.json"),
            os.path.join(self.data_dir, "product_rows.json"),
            os.path.join(self.data_dir, "crawl_results.json"),
            os.path.join(self.script_dir, "products.json"),
            os.path.join(self.script_dir, "crawl_results.json"),
            os.path.join(self.script_dir, "musinsa_products.json"),
        ]
        return any(os.path.exists(path) for path in candidates)

    def _load_json_rows(self, path: str) -> list[ProductRow]:
        if not os.path.exists(path):
            return []
        try:
            data = _read_json_payload(path, os.path.getmtime(path))
        except Exception:
            return []
        records = data.get("products") if isinstance(data, dict) else data
        if not isinstance(records, list):
            return []
        return [self._product_from_mapping(item, str(idx + 1), "local") for idx, item in enumerate(records) if isinstance(item, dict)]

    def _rows_from_sheet_values(self, values: list[list[str]], sheet_name: str) -> list[ProductRow]:
        if not values:
            return []
        header = [str(cell).strip() for cell in values[0]]
        has_header = any(self._canonical_name(cell) for cell in header)
        rows = values[1:] if has_header else values
        result = []
        for idx, row in enumerate(rows, start=1):
            if not any(str(cell).strip() for cell in row):
                continue
            if has_header:
                record = {header[col]: row[col] if col < len(row) else "" for col in range(len(header))}
                result.append(self._product_from_mapping(record, str(idx), sheet_name, row))
            else:
                result.append(self._product_from_sequence(row, str(idx), sheet_name))
        return result

    def _product_from_mapping(self, record: dict, fallback_no: str, sheet: str, row: list[str] | None = None) -> ProductRow:
        def pick(*keys: str) -> str:
            lowered = {str(k).strip().lower(): v for k, v in record.items()}
            for key in keys:
                if key in record and str(record.get(key, "")).strip():
                    return str(record.get(key, "")).strip()
                value = lowered.get(key.lower())
                if value is not None and str(value).strip():
                    return str(value).strip()
            for raw_key, value in record.items():
                canonical = self._canonical_name(str(raw_key))
                if canonical in keys and str(value).strip():
                    return str(value).strip()
            return ""

        cells = [str(cell).strip() for cell in (row or [])]
        get = lambda idx, default="": cells[idx] if idx < len(cells) else default
        state = pick("state", "status", "상태", "작업상태", "진행상태")
        name = get(SHEET_COL_NAME_KR) or pick("name", "상품명", "product_name", "product_name_kr", "title")
        category = self._pick_dashboard_category(
            get(SHEET_COL_MUSINSA_SUBCATEGORY),
            pick("무신사소분류", "musinsa_subcategory", "musinsa_small_category", "소분류"),
            get(SHEET_COL_CATEGORY_BUYMA),
            pick("category", "카테고리", "buyma_category", "buyma_cat", "category_name"),
        )
        price = get(SHEET_COL_PRICE_BUYMA) or pick("price", "가격", "buyma_price", "판매가", "price_yen", "yen_price")
        return ProductRow(
            no=pick("no", "번호", "id", "상품코드") or fallback_no,
            state=state or "대기",
            name=name,
            brand=get(3) or pick("brand", "브랜드", "brand_en"),
            category=category,
            price=price,
            sheet=sheet,
            updated=pick("updated", "최종 업데이트", "updated_at", "timestamp") or datetime.now().strftime("%H:%M:%S"),
            action="재실행 / 열기" if self._is_error(state) else "실행 / 열기",
        )

    def _product_from_sequence(self, row: list[str], fallback_no: str, sheet: str) -> ProductRow:
        cells = [str(cell).strip() for cell in row]
        get = lambda idx, default="": cells[idx] if idx < len(cells) else default
        state = get(0) or "대기"
        name = get(SHEET_COL_NAME_KR) or get(1)
        brand = get(3)
        category = self._pick_dashboard_category(
            get(SHEET_COL_MUSINSA_SUBCATEGORY),
            get(SHEET_COL_CATEGORY_BUYMA),
            get(4),
        )
        price = get(SHEET_COL_PRICE_BUYMA) or get(5)
        return ProductRow(
            no=fallback_no,
            state=state,
            name=name,
            brand=brand,
            category=category,
            price=price,
            sheet=sheet,
            updated=get(6) or datetime.now().strftime("%H:%M:%S"),
            action="재실행 / 열기" if self._is_error(state) else "실행 / 열기",
        )

    def _canonical_name(self, text: str) -> str:
        normalized = re.sub(r"[\s_/-]+", "", text.strip().lower())
        mapping = {
            "상태": "state",
            "작업상태": "state",
            "진행상태": "state",
            "상품명": "name",
            "브랜드": "brand",
            "카테고리": "category",
            "가격": "price",
            "최종업데이트": "updated",
        }
        return mapping.get(normalized, normalized)

    def _running_count(self) -> int:
        count = 1 if self.process_manager.is_running() else 0
        for team_key in self.pipeline_service.team_watch_actions:
            if self.process_manager.is_team_running(team_key):
                count += 1
        return count

    def _stage_from_event(self, event: LogEvent) -> str:
        category = event.category.lower()
        if category in {"scout", "정찰"}:
            return "scout"
        if category in {"assets", "image", "이미지"}:
            return "assets"
        if category in {"design", "thumbnail", "썸네일"}:
            return "design"
        if category in {"sales", "upload", "업로드", "buyma"}:
            return "sales"
        return self.pipeline_service.stage_from_log(event.message)

    def _looks_like_product_success(self, event: LogEvent) -> bool:
        text = event.message.lower()
        return any(word.lower() in text for word in DONE_WORDS) and "작업 종료" not in text

    def _looks_like_product_failure(self, event: LogEvent) -> bool:
        if event.level.upper() == "ERROR":
            return True
        text = event.message.lower()
        return any(word.lower() in text for word in ERROR_WORDS)

    def _count_rows_matching(self, rows: Iterable[ProductRow], words: Iterable[str]) -> int:
        count = 0
        for row in rows:
            haystack = f"{row.state} {row.action}".lower()
            if any(word.lower() in haystack for word in words if word):
                count += 1
        return count

    def _matches_words(self, text: str, words: Iterable[str]) -> bool:
        haystack = str(text or "").lower()
        return any(str(word or "").lower() in haystack for word in words if str(word or ""))

    def _group_count(self, rows: Iterable[ProductRow], key_fn) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for row in rows:
            key = str(key_fn(row) or "미분류").strip() or "미분류"
            counts[key] = counts.get(key, 0) + 1
        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))

    def _is_done(self, state: str) -> bool:
        return any(word.lower() in str(state).lower() for word in DONE_WORDS)

    def _is_error(self, state: str) -> bool:
        return any(word.lower() in str(state).lower() for word in ERROR_WORDS)

    def _is_waiting(self, state: str) -> bool:
        text = str(state or "").lower()
        return not self._is_done(text) and not self._is_error(text) and any(word.lower() in text for word in WAITING_WORDS)

    def _is_today(self, value: str) -> bool:
        text = str(value or "").strip()
        today = datetime.now().date()
        if not text:
            return False
        if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", text):
            return True
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
            try:
                return datetime.strptime(text[:19], fmt).date() == today
            except Exception:
                continue
        return False

    def _is_valid_product_row(self, row: ProductRow) -> bool:
        def _clean(value: str) -> str:
            text = str(value or "").strip()
            lowered = text.lower()
            if lowered in {"", "nan", "none", "#value!"}:
                return ""
            return text

        name = _clean(row.name)
        brand = _clean(row.brand)
        # Dashboard totals should ignore template/empty rows even if formulas
        # left category/price-like artifacts in the sheet.
        return bool(name or brand)

    def _pick_dashboard_category(self, *candidates: str) -> str:
        for candidate in candidates:
            value = str(candidate or "").strip()
            if not value:
                continue
            if self._looks_like_price_text(value):
                continue
            return value
        return ""

    def _looks_like_price_text(self, value: str) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        lowered = text.lower().replace(",", "").replace(" ", "")
        if lowered.startswith("¥") or lowered.startswith("₩") or lowered.startswith("$"):
            return True
        if lowered.endswith("원") or lowered.endswith("엔"):
            return True
        if re.fullmatch(r"[0-9]+(\.[0-9]+)?", lowered):
            return True
        return False

    def _safe_path(self, path: str) -> str:
        if not path:
            return "-"
        return os.path.abspath(os.path.expanduser(path))

    def _load_recent_log_lines(self, *, limit: int = 30, categories: set[str] | None = None) -> list[str]:
        path = os.path.join(self.data_dir, "logs", f"launcher-{datetime.now():%Y-%m-%d}.log")
        if not os.path.exists(path):
            return []
        lines: list[str] = []
        try:
            payloads = _read_log_payloads(path, os.path.getmtime(path))
        except Exception:
            return []
        for payload in payloads:
            category = str(payload.get("category") or "")
            if categories and category not in categories:
                continue
            timestamp = str(payload.get("timestamp") or "")[-8:]
            level = str(payload.get("level") or "INFO")
            message = str(payload.get("message") or "").strip()
            if not message:
                continue
            lines.append(f"[{timestamp}] [{level}] [{category}] {message}")
        return lines[-limit:]

    def _load_upload_recovery_stats(self) -> dict:
        counts = {"alias": 0, "fuzzy": 0, "same_parent_fallback": 0, "other": 0}
        attempts = 0
        successes = 0
        for line in self._load_recent_log_lines(limit=500, categories={"buyma", "sales", "process"}):
            if "[category][recovery]" not in line:
                continue
            method_match = re.search(r"method=([a-z_]+)", line)
            method = method_match.group(1) if method_match else ""
            if method in counts:
                if "success" in line.lower():
                    counts[method] += 1
                    successes += 1
                if "try=" in line:
                    attempts += 1
        return {
            "counts": counts,
            "success_ratio": successes / max(1, attempts),
        }
