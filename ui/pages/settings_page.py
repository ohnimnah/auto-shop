from __future__ import annotations

import difflib
import json
import os
import shutil
import ssl
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from config.config_service import get_profile_config_path, load_config, save_config
from ui.pages.base_page import BasePage, SECTION_GAP


def _same_file(source_path: str, target_path: str) -> bool:
    try:
        return os.path.samefile(source_path, target_path)
    except OSError:
        return os.path.abspath(source_path) == os.path.abspath(target_path)


class SettingsPage(BasePage):
    TAB_SPECS = (
        ("general", "기본 설정"),
        ("crawling", "크롤링 설정"),
        ("upload", "업로드 설정"),
        ("notification", "알림 설정"),
        ("advanced", "고급 설정"),
    )
    GENERAL_TAB_FIELDS = (
        ("product_input", "product_input"),
        ("category", "category"),
        ("candidate", "candidate"),
        ("scout_queue", "scout_queue"),
        ("log", "log"),
        ("category_mapping_candidates", "category_mapping_candidates"),
    )

    def __init__(self, parent: tk.Widget, controller) -> None:
        super().__init__(parent, controller, title="관리 / 설정", subtitle="시스템 설정을 탭별로 편집하고 검증합니다.")
        self.active_tab = tk.StringVar(value="general")
        self.last_saved_config: dict | None = None
        self.available_sheet_tabs: list[str] = []
        self._sheet_tabs_auto_loaded = False
        self._suspend_page_scroll = False
        self.sheet_validation_rows: list[tuple[str, str, str, str, str]] = []
        self.validation_after_id: str | None = None
        self.tab_buttons: dict[str, tk.Widget] = {}
        self.sheet_comboboxes: dict[str, ttk.Combobox] = {}
        self._init_status_vars()
        self._init_config_vars()
        self._load_config_into_vars()
        self._bind_live_validation()
        self.build()

    def _init_status_vars(self) -> None:
        self.connection_status_var = tk.StringVar(value="⚠ 연결 테스트 전")
        self.permission_status_var = tk.StringVar(value="⚠ 권한 확인 전")
        self.tabs_status_var = tk.StringVar(value="⚠ 시트 탭 확인 전")
        self.validation_summary_var = tk.StringVar(value="입력값을 수정하면 자동으로 기본 검증을 실행합니다.")
        self.last_saved_var = tk.StringVar(value="-")
        self.config_path_var = tk.StringVar(value=self._config_path())
        self.telegram_status_var = tk.StringVar(value="테스트 전")
        self.buyma_status_var = tk.StringVar(value="계정 확인 전")
        self.connection_color_var = tk.StringVar(value=self.controller.theme["muted"])
        self.permission_color_var = tk.StringVar(value=self.controller.theme["muted"])
        self.tabs_color_var = tk.StringVar(value=self.controller.theme["muted"])
        self.diff_hint_var = tk.StringVar(value="저장 전 변경사항을 확인할 수 있습니다.")

    def _init_config_vars(self) -> None:
        self.profile_display_var = tk.StringVar(value=self.controller.profile_name)
        self.spreadsheet_id_var = tk.StringVar()
        self.service_account_path_var = tk.StringVar()
        self.images_dir_var = tk.StringVar()
        self.log_dir_var = tk.StringVar()
        self.thumbnail_footer_suffix_var = tk.StringVar()
        self.buyma_email_var = tk.StringVar()
        self.buyma_password_var = tk.StringVar()
        self.general_tab_vars = {key: tk.StringVar() for key, _label in self.GENERAL_TAB_FIELDS}

        self.crawling_vars = {
            "max_pages": tk.StringVar(),
            "delay_seconds": tk.StringVar(),
            "retry_count": tk.StringVar(),
            "timeout": tk.StringVar(),
            "keyword": tk.StringVar(),
            "min_price": tk.StringVar(),
            "max_price": tk.StringVar(),
            "min_reviews": tk.StringVar(),
            "min_sales": tk.StringVar(),
            "category_pages": tk.BooleanVar(),
            "product_detail_pages": tk.BooleanVar(),
            "brand_pages": tk.BooleanVar(),
            "keyword_search": tk.BooleanVar(),
            "download_images": tk.BooleanVar(),
            "generate_thumbnails": tk.BooleanVar(),
            "save_html": tk.BooleanVar(),
            "dedupe": tk.BooleanVar(),
        }
        self.upload_vars = {
            "batch_size": tk.StringVar(),
            "max_workers": tk.StringVar(),
            "retry_count": tk.StringVar(),
            "source_category": tk.StringVar(),
            "target_buyma_category": tk.StringVar(),
            "markup_percent": tk.StringVar(),
            "minimum_margin": tk.StringVar(),
            "rounding_rule": tk.StringVar(),
            "validate_before_upload": tk.BooleanVar(),
            "retry_failed": tk.BooleanVar(),
            "save_logs": tk.BooleanVar(),
            "auto_price": tk.BooleanVar(),
        }
        self.notification_vars = {
            "telegram_enabled": tk.BooleanVar(),
            "telegram_bot_token": tk.StringVar(),
            "telegram_chat_id": tk.StringVar(),
            "notify_start": tk.BooleanVar(),
            "notify_complete": tk.BooleanVar(),
            "notify_error": tk.BooleanVar(),
            "notify_important": tk.BooleanVar(),
            "email_enabled": tk.BooleanVar(),
            "email_address": tk.StringVar(),
            "email_password": tk.StringVar(),
            "schedule_start": tk.StringVar(),
            "schedule_end": tk.StringVar(),
            "schedule_timezone": tk.StringVar(),
        }
        self.advanced_vars = {
            "python_path": tk.StringVar(),
            "chrome_path": tk.StringVar(),
            "execution_max_workers": tk.StringVar(),
            "cpu_limit": tk.StringVar(),
            "memory_limit": tk.StringVar(),
            "async_mode": tk.BooleanVar(),
            "smart_retry": tk.BooleanVar(),
            "ai_category": tk.BooleanVar(),
        }

    def build(self) -> None:
        self.build_header()
        self._build_metrics_row()
        self.body.grid_rowconfigure(0, weight=0)
        self.body.grid_rowconfigure(1, weight=0)
        self.body.grid_rowconfigure(2, weight=1)
        self.body.grid_rowconfigure(3, weight=0)
        self.body.grid_columnconfigure(0, weight=1)

        top = tk.Frame(self.body, bg=self.controller.theme["bg"])
        top.grid(row=1, column=0, sticky="ew", pady=(0, SECTION_GAP))
        top.grid_columnconfigure(0, weight=1)
        self._build_context_bar(top)
        self._build_tab_bar(top)

        self.content = tk.Frame(self.body, bg=self.controller.theme["bg"])
        self.content.grid(row=2, column=0, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self.content_canvas = tk.Canvas(self.content, bg=self.controller.theme["bg"], highlightthickness=0)
        self.content_canvas.grid(row=0, column=0, sticky="nsew")
        self.content_scrollbar = ttk.Scrollbar(self.content, orient=tk.VERTICAL, command=self.content_canvas.yview)
        self.content_scrollbar.grid(row=0, column=1, sticky="ns")
        self.content_canvas.configure(yscrollcommand=self.content_scrollbar.set)
        self.content_viewport = tk.Frame(self.content_canvas, bg=self.controller.theme["bg"])
        self._content_window = self.content_canvas.create_window((0, 0), window=self.content_viewport, anchor="nw")
        self.content_viewport.bind("<Configure>", self._on_content_configure)
        self.content_canvas.bind("<Configure>", self._on_content_canvas_configure)
        self.content_canvas.bind("<Enter>", self._bind_mousewheel)
        self.content_canvas.bind("<Leave>", self._unbind_mousewheel)

        self.action_bar = tk.Frame(self.body, bg=self.controller.theme["panel"], highlightbackground=self.controller.theme["line"], highlightthickness=1, padx=12, pady=10)
        self.action_bar.grid(row=3, column=0, sticky="ew", pady=(SECTION_GAP, 0))
        self._build_action_bar(self.action_bar)

        self._render_active_tab()

    def _build_metrics_row(self) -> None:
        metrics = [
            ("현재 프로필", 1, self.controller.profile_name),
            ("시트 탭 수", sum(1 for var in self.general_tab_vars.values() if var.get().strip()), "설정됨"),
            ("경로 설정", 2 if self.images_dir_var.get().strip() and self.log_dir_var.get().strip() else 0, "이미지 / 로그"),
            ("BUYMA 계정", 1 if self.buyma_email_var.get().strip() else 0, "이메일 저장"),
        ]
        accents = [
            self.controller.theme["blue"],
            self.controller.theme["green"],
            self.controller.theme["red"],
            self.controller.theme["yellow"],
        ]
        self.build_metric_row(self.body, row=0, metrics=metrics, accents=accents)

    def _build_context_bar(self, parent: tk.Widget) -> None:
        row = tk.Frame(parent, bg=self.controller.theme["bg"])
        row.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        row.grid_columnconfigure(0, weight=1)
        tk.Label(row, text="현재 프로필:", bg=self.controller.theme["bg"], fg=self.controller.theme["muted"], font=("Segoe UI", 8, "bold")).grid(row=0, column=1, sticky="e", padx=(0, 6))
        ttk.Combobox(row, values=[self.controller.profile_name], textvariable=self.profile_display_var, state="readonly", width=16).grid(row=0, column=2, sticky="e")
        self.controller._mini_button(
            row,
            "프로필 편집",
            lambda: self.controller.dispatch_ui_action("설정: 프로필 변경", self.controller.configure_user_profile, category="settings"),
            "#1e3350",
            "#294565",
        ).grid(row=0, column=3, sticky="e", padx=(10, 10))
        tk.Label(row, textvariable=self.last_saved_var, bg=self.controller.theme["bg"], fg=self.controller.theme["muted"], font=("Segoe UI", 8)).grid(row=0, column=4, sticky="e")

    def _build_tab_bar(self, parent: tk.Widget) -> None:
        row = tk.Frame(parent, bg=self.controller.theme["bg"])
        row.grid(row=1, column=0, sticky="ew")
        row.grid_columnconfigure(0, weight=1)
        left = tk.Frame(row, bg=self.controller.theme["bg"])
        left.grid(row=0, column=0, sticky="w")
        for key, label in self.TAB_SPECS:
            btn = self.controller._mini_button(
                left,
                label,
                lambda target=key: self._set_active_tab(target),
                self.controller.theme["blue"] if key == self.active_tab.get() else "#111f34",
                self.controller.theme["blue_2"] if key == self.active_tab.get() else "#1e3350",
            )
            btn.pack(side=tk.LEFT, padx=(0, 8))
            self.tab_buttons[key] = btn
        tk.Label(
            row,
            text="변경사항은 저장 전까지 프로필에만 반영됩니다.",
            bg="#2b1d00",
            fg="#fbbf24",
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=4,
        ).grid(row=0, column=1, sticky="e")

    def _set_active_tab(self, tab_key: str) -> None:
        self.active_tab.set(tab_key)
        for key, button in self.tab_buttons.items():
            is_active = key == tab_key
            button.configure(
                bg=self.controller.theme["blue"] if is_active else "#111f34",
                activebackground=self.controller.theme["blue_2"] if is_active else "#1e3350",
            )
        self._render_active_tab()
        self.after_idle(lambda: self.content_canvas.yview_moveto(0.0))

    def _render_active_tab(self) -> None:
        for child in self.content_viewport.winfo_children():
            child.destroy()
        self.content_viewport.grid_columnconfigure(0, weight=7)
        self.content_viewport.grid_columnconfigure(1, weight=3)
        self.content_viewport.grid_rowconfigure(0, weight=1)
        left = tk.Frame(self.content_viewport, bg=self.controller.theme["bg"])
        right = tk.Frame(self.content_viewport, bg=self.controller.theme["bg"])
        left.grid(row=0, column=0, sticky="nsew", padx=(0, SECTION_GAP))
        right.grid(row=0, column=1, sticky="nsew")
        left.grid_columnconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)
        builder = {
            "general": self._build_general_tab,
            "crawling": self._build_crawling_tab,
            "upload": self._build_upload_tab,
            "notification": self._build_notification_tab,
            "advanced": self._build_advanced_tab,
        }[self.active_tab.get()]
        builder(left, right)
        if self.active_tab.get() == "general":
            self.after_idle(self._maybe_autoload_google_sheet_tabs)
        self.after_idle(self._refresh_content_scroll_region)

    def _on_content_configure(self, _event=None) -> None:
        self._refresh_content_scroll_region()

    def _on_content_canvas_configure(self, event=None) -> None:
        if event is not None:
            self.content_canvas.itemconfigure(self._content_window, width=event.width)
        self._refresh_content_scroll_region()

    def _refresh_content_scroll_region(self) -> None:
        try:
            self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))
        except Exception:
            pass

    def _bind_mousewheel(self, _event=None) -> None:
        self.content_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.content_canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.content_canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event=None) -> None:
        self.content_canvas.unbind_all("<MouseWheel>")
        self.content_canvas.unbind_all("<Button-4>")
        self.content_canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event) -> None:
        event_widget = getattr(event, "widget", None)
        if not self._is_widget_in_scroll_region(event_widget):
            return
        if self._suspend_page_scroll or self._is_combobox_dropdown_active() or self._is_combobox_popup_widget(event_widget):
            return
        try:
            if getattr(event, "num", None) == 4:
                delta = -1
            elif getattr(event, "num", None) == 5:
                delta = 1
            else:
                raw_delta = getattr(event, "delta", 0)
                delta = -1 if raw_delta > 0 else 1
            self.content_canvas.yview_scroll(delta, "units")
        except Exception:
            pass

    def _suspend_scroll_for_dropdown(self) -> None:
        self._suspend_page_scroll = True

    def _resume_scroll_after_dropdown(self, _event=None) -> None:
        self.after(120, lambda: setattr(self, "_suspend_page_scroll", False))

    def _is_widget_in_scroll_region(self, widget: tk.Widget | None) -> bool:
        if widget is None:
            return False
        current = widget
        for _ in range(20):
            if current is self.content_canvas or current is self.content_viewport or current is self.content:
                return True
            try:
                parent_name = current.winfo_parent()
                if not parent_name:
                    break
                current = current.nametowidget(parent_name)
            except Exception:
                break
        return False

    def _is_combobox_popup_widget(self, widget: tk.Widget | None) -> bool:
        if widget is None:
            return False
        current = widget
        for _ in range(12):
            try:
                widget_class = str(current.winfo_class() or "")
                widget_path = str(current).lower()
            except Exception:
                return False
            if widget_class in {"Listbox", "TCombobox"}:
                return True
            if "popdown" in widget_path:
                return True
            try:
                parent_name = current.winfo_parent()
                if not parent_name:
                    break
                current = current.nametowidget(parent_name)
            except Exception:
                break
        return False

    def _is_combobox_dropdown_active(self) -> bool:
        try:
            pointer_x = self.winfo_pointerx()
            pointer_y = self.winfo_pointery()
            widget = self.winfo_containing(pointer_x, pointer_y)
            if widget is None:
                return False
            return self._is_combobox_popup_widget(widget)
        except Exception:
            return False
        return False

    def _build_auto_card(self, parent: tk.Widget, title: str, *, title_suffix: str = "") -> tuple[tk.Frame, tk.Frame]:
        card = self.controller._panel(parent, padx=12, pady=10)
        card.grid_columnconfigure(0, weight=1)
        header = tk.Frame(card, bg=self.controller.theme["panel"])
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.grid_columnconfigure(0, weight=1)
        tk.Label(
            header,
            text=title,
            bg=self.controller.theme["panel"],
            fg=self.controller.theme["text"],
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="w")
        if title_suffix:
            tk.Label(
                header,
                text=title_suffix,
                bg=self.controller.theme["panel"],
                fg=self.controller.theme["muted"],
                font=("Segoe UI", 8),
            ).grid(row=0, column=1, sticky="e")
        body = tk.Frame(card, bg=self.controller.theme["panel"])
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        return card, body

    def _combo_values_for(self, current_value: str) -> list[str]:
        values = [value.strip() for value in self.available_sheet_tabs if value and value.strip()]
        current = current_value.strip()
        if current and current not in values:
            values.insert(0, current)
        return values

    def _update_sheet_combobox_values(self) -> None:
        for key, combo in self.sheet_comboboxes.items():
            combo.configure(values=self._combo_values_for(self.general_tab_vars[key].get()))

    def _maybe_autoload_google_sheet_tabs(self) -> None:
        if self._sheet_tabs_auto_loaded or self.available_sheet_tabs:
            return
        if not self.controller._is_valid_spreadsheet_id(self.spreadsheet_id_var.get()):
            return
        credentials_path = os.path.abspath(os.path.expanduser(self.service_account_path_var.get().strip()))
        if not credentials_path or not os.path.isfile(credentials_path):
            return
        self._sheet_tabs_auto_loaded = True
        self.load_google_sheet_tabs(silent=True)

    def _build_action_bar(self, parent: tk.Widget) -> None:
        parent.grid_columnconfigure(0, weight=1)
        tk.Label(parent, textvariable=self.diff_hint_var, bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 8)).grid(row=0, column=0, sticky="w")
        buttons = tk.Frame(parent, bg=self.controller.theme["panel"])
        buttons.grid(row=0, column=1, sticky="e")
        self.controller._mini_button(buttons, "변경사항 보기 (Diff)", lambda: self.controller.dispatch_ui_action("설정: diff 보기", self.show_config_diff, category="settings"), "#111f34", "#1e3350").pack(side=tk.LEFT, padx=(0, 8))
        self.controller._mini_button(buttons, "Save Config", lambda: self.controller.dispatch_ui_action("설정: config 저장", self.save_current_config, category="settings"), self.controller.theme["blue"], self.controller.theme["blue_2"]).pack(side=tk.LEFT, padx=(0, 8))
        self.controller._mini_button(buttons, "Apply (적용)", lambda: self.controller.dispatch_ui_action("설정: 적용", self.apply_config, category="settings"), self.controller.theme["green"], self.controller.theme["green"]).pack(side=tk.LEFT, padx=(0, 8))
        self.controller._mini_button(buttons, "Cancel", lambda: self.controller.dispatch_ui_action("설정: 취소", self.reset_to_saved_config, category="settings"), "#334155", "#475569").pack(side=tk.LEFT)

    def _build_general_tab(self, left: tk.Widget, right: tk.Widget) -> None:
        self._build_google_sheet_card(left, 0)
        self._build_sheet_tabs_card(left, 1)
        lower = tk.Frame(left, bg=self.controller.theme["bg"])
        lower.grid(row=2, column=0, sticky="ew")
        lower.grid_columnconfigure(0, weight=1, uniform="general_lower")
        lower.grid_columnconfigure(1, weight=1, uniform="general_lower")
        self._build_paths_card(lower, 0, 0, padx=(0, SECTION_GAP // 2))
        self._build_buyma_card(lower, 0, 1, padx=(SECTION_GAP // 2, 0))
        self._build_status_panel(right)
        self._build_sheet_validation_panel(right)
        self._build_info_panel(right, title="작업 정보", body_rows=[("마지막 저장", self.last_saved_var), ("설정 파일 경로", self.config_path_var)])

    def _build_crawling_tab(self, left: tk.Widget, right: tk.Widget) -> None:
        self._build_form_card(
            left,
            0,
            "크롤링 기본 설정",
            [
                ("최대 동시 크롤링 수", self.crawling_vars["max_pages"]),
                ("페이지 간 대기 시간 (초)", self.crawling_vars["delay_seconds"]),
                ("재시도 횟수", self.crawling_vars["retry_count"]),
                ("요청 타임아웃 (초)", self.crawling_vars["timeout"]),
            ],
        )
        self._build_targets_card(left, 1)
        self._build_form_card(
            left,
            2,
            "크롤링 필터",
            [
                ("최소 가격", self.crawling_vars["min_price"]),
                ("최대 가격", self.crawling_vars["max_price"]),
                ("최소 리뷰 수", self.crawling_vars["min_reviews"]),
                ("최소 판매 수", self.crawling_vars["min_sales"]),
            ],
            columns=2,
        )
        self._build_toggle_card(
            right,
            0,
            "기타 옵션",
            [
                ("이미지 다운로드", self.crawling_vars["download_images"]),
                ("썸네일 생성", self.crawling_vars["generate_thumbnails"]),
                ("HTML 저장", self.crawling_vars["save_html"]),
                ("중복 상품 필터링", self.crawling_vars["dedupe"]),
            ],
        )
        self._build_info_panel(right, title="크롤링 안내", body_rows=[("현재 키워드", self.crawling_vars["keyword"]), ("검증 상태", self.validation_summary_var)], row=1)

    def _build_upload_tab(self, left: tk.Widget, right: tk.Widget) -> None:
        self._build_form_card(
            left,
            0,
            "업로드 기본 설정",
            [
                ("배치 크기", self.upload_vars["batch_size"]),
                ("동시 워커 수", self.upload_vars["max_workers"]),
                ("재시도 횟수", self.upload_vars["retry_count"]),
            ],
            columns=3,
        )
        self._build_form_card(
            left,
            1,
            "카테고리 매핑",
            [
                ("source category", self.upload_vars["source_category"]),
                ("target BUYMA category", self.upload_vars["target_buyma_category"]),
            ],
        )
        self._build_form_card(
            left,
            2,
            "가격 설정",
            [
                ("markup (%)", self.upload_vars["markup_percent"]),
                ("minimum margin", self.upload_vars["minimum_margin"]),
                ("rounding rule", self.upload_vars["rounding_rule"]),
            ],
            columns=3,
        )
        self._build_toggle_card(
            left,
            3,
            "업로드 옵션",
            [
                ("업로드 전 검증", self.upload_vars["validate_before_upload"]),
                ("실패 시 재시도", self.upload_vars["retry_failed"]),
                ("로그 저장", self.upload_vars["save_logs"]),
                ("자동 가격 계산", self.upload_vars["auto_price"]),
            ],
        )
        self._build_info_panel(
            right,
            title="업로드 요약",
            body_rows=[
                ("배치 크기", self.upload_vars["batch_size"]),
                ("라운딩 규칙", self.upload_vars["rounding_rule"]),
                ("현재 검증 상태", self.validation_summary_var),
            ],
            row=0,
        )
        self._build_info_panel(
            right,
            title="카테고리 메모",
            body_rows=[
                ("source", self.upload_vars["source_category"]),
                ("target", self.upload_vars["target_buyma_category"]),
            ],
            row=1,
        )

    def _build_notification_tab(self, left: tk.Widget, right: tk.Widget) -> None:
        self._build_telegram_card(left, 0)
        self._build_toggle_card(
            left,
            1,
            "알림 이벤트",
            [
                ("작업 시작", self.notification_vars["notify_start"]),
                ("작업 완료", self.notification_vars["notify_complete"]),
                ("오류 발생", self.notification_vars["notify_error"]),
                ("중요 이벤트", self.notification_vars["notify_important"]),
            ],
        )
        self._build_email_card(left, 2)
        self._build_form_card(
            right,
            0,
            "알림 시간 설정",
            [
                ("시작 시간", self.notification_vars["schedule_start"]),
                ("종료 시간", self.notification_vars["schedule_end"]),
                ("Timezone", self.notification_vars["schedule_timezone"]),
            ],
        )
        self._build_info_panel(
            right,
            title="알림 상태",
            body_rows=[
                ("Telegram 테스트", self.telegram_status_var),
                ("현재 검증 상태", self.validation_summary_var),
            ],
            row=1,
        )

    def _build_advanced_tab(self, left: tk.Widget, right: tk.Widget) -> None:
        self._build_form_card(
            left,
            0,
            "시스템 경로",
            [
                ("Python path", self.advanced_vars["python_path"]),
                ("Chrome path", self.advanced_vars["chrome_path"]),
            ],
        )
        self._build_form_card(
            left,
            1,
            "실행 설정",
            [
                ("max_workers", self.advanced_vars["execution_max_workers"]),
                ("CPU usage limit (%)", self.advanced_vars["cpu_limit"]),
                ("memory limit (MB)", self.advanced_vars["memory_limit"]),
            ],
            columns=3,
        )
        self._build_toggle_card(
            left,
            2,
            "실험 기능",
            [
                ("비동기 모드", self.advanced_vars["async_mode"]),
                ("스마트 재시도", self.advanced_vars["smart_retry"]),
                ("AI 카테고리 추천", self.advanced_vars["ai_category"]),
            ],
        )
        self._build_action_only_card(
            right,
            0,
            "데이터 관리",
            [
                ("캐시 삭제", self._clear_runtime_cache, "#111f34", "#1e3350"),
                ("로그 정리", self._clear_log_files, "#111f34", "#1e3350"),
                ("설정 초기화", self._reset_config_defaults, "#7f1d1d", "#991b1b"),
            ],
        )
        self._build_info_panel(
            right,
            title="고급 설정 안내",
            body_rows=[
                ("현재 Python", self.advanced_vars["python_path"]),
                ("현재 Chrome", self.advanced_vars["chrome_path"]),
            ],
            row=1,
        )

    def _build_google_sheet_card(self, parent: tk.Widget, row: int) -> None:
        card, body = self._build_auto_card(parent, "Google Sheets")
        card.grid(row=row, column=0, sticky="ew", pady=(0, SECTION_GAP))
        self._build_entry_row(body, 0, "Spreadsheet ID", self.spreadsheet_id_var)
        self._build_entry_row(body, 2, "서비스 계정 JSON 경로", self.service_account_path_var, button_text="파일 선택", button_command=self._choose_service_account_file)
        button_row = tk.Frame(body, bg=self.controller.theme["panel"])
        button_row.grid(row=4, column=0, columnspan=2, sticky="e", pady=(8, 0))
        self.controller._mini_button(button_row, "탭 목록 불러오기", lambda: self.controller.dispatch_ui_action("설정: 탭 목록 불러오기", self.load_google_sheet_tabs, category="settings"), "#1e3350", "#294565").pack(side=tk.RIGHT)

    def _build_sheet_tabs_card(self, parent: tk.Widget, row: int) -> None:
        card, body = self._build_auto_card(parent, "Sheet Tabs")
        card.grid(row=row, column=0, sticky="ew", pady=(0, SECTION_GAP))
        body.grid_columnconfigure(0, weight=1, uniform="sheet_tabs")
        body.grid_columnconfigure(1, weight=1, uniform="sheet_tabs")
        for idx, (key, label) in enumerate(self.GENERAL_TAB_FIELDS):
            col = idx % 2
            block_row = (idx // 2) * 2
            combo = self._build_combo_field(body, block_row, col, label, self.general_tab_vars[key], values=self._combo_values_for(self.general_tab_vars[key].get()))
            self.sheet_comboboxes[key] = combo

    def _build_paths_card(self, parent: tk.Widget, row: int, column: int, *, padx: tuple[int, int]) -> None:
        card, body = self._build_auto_card(parent, "Paths")
        card.grid(row=row, column=column, sticky="ew", padx=padx)
        self._build_entry_row(body, 0, "images_dir", self.images_dir_var, button_text="폴더 선택", button_command=lambda: self._choose_directory(self.images_dir_var))
        self._build_entry_row(body, 2, "log_dir", self.log_dir_var, button_text="폴더 선택", button_command=lambda: self._choose_directory(self.log_dir_var))
        self._build_entry_row(body, 4, "thumbnail_footer_suffix", self.thumbnail_footer_suffix_var)

    def _build_buyma_card(self, parent: tk.Widget, row: int, column: int, *, padx: tuple[int, int]) -> None:
        card, body = self._build_auto_card(parent, "BUYMA Account")
        card.grid(row=row, column=column, sticky="ew", padx=padx)
        body.grid_columnconfigure(0, weight=1, uniform="buyma")
        body.grid_columnconfigure(1, weight=1, uniform="buyma")
        self._build_inline_entry(body, 0, 0, "email", self.buyma_email_var)
        self._build_inline_entry(body, 0, 1, "password", self.buyma_password_var, show="*")
        tk.Label(body, text="비밀번호는 저장 시 OS 키체인에 보관됩니다.", bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 8), wraplength=220, justify=tk.LEFT).grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.controller._mini_button(body, "연결 테스트", lambda: self.controller.dispatch_ui_action("설정: BUYMA 연결 테스트", self.test_buyma_credentials, category="settings"), "#1e3350", "#294565").grid(row=2, column=1, sticky="e", pady=(6, 0))

    def _build_status_panel(self, parent: tk.Widget) -> None:
        card, body = self._build_auto_card(parent, "연결 상태")
        card.grid(row=0, column=0, sticky="ew", pady=(0, SECTION_GAP))
        self._build_status_row(body, 0, "Google Sheets 연결", self.connection_status_var, self.connection_color_var)
        self._build_status_row(body, 1, "권한 상태", self.permission_status_var, self.permission_color_var)
        self._build_status_row(body, 2, "시트 탭 상태", self.tabs_status_var, self.tabs_color_var)
        tk.Label(body, textvariable=self.validation_summary_var, bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 8), wraplength=320, justify=tk.LEFT).grid(row=3, column=0, sticky="ew", pady=(8, 0))

    def _build_sheet_validation_panel(self, parent: tk.Widget) -> None:
        card, body = self._build_auto_card(parent, "시트 탭 검증 결과")
        card.grid(row=1, column=0, sticky="nsew", pady=(0, SECTION_GAP))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        columns = ("tab_name", "status", "rows", "cols", "note")
        self.validation_table = ttk.Treeview(body, columns=columns, show="headings", style="Ops.Treeview", height=7)
        headings = {"tab_name": "탭 이름", "status": "상태", "rows": "행 수", "cols": "열 수", "note": "비고"}
        widths = {"tab_name": 150, "status": 60, "rows": 50, "cols": 50, "note": 70}
        for col in columns:
            self.validation_table.heading(col, text=headings[col])
            self.validation_table.column(col, width=widths[col], minwidth=widths[col], stretch=(col == "tab_name"))
        self.validation_table.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(body, orient=tk.VERTICAL, command=self.validation_table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.validation_table.configure(yscrollcommand=scroll.set)
        self.validation_table.tag_configure("ok", foreground="#4ade80")
        self.validation_table.tag_configure("error", foreground="#f87171")
        self.validation_table.tag_configure("pending", foreground="#cbd5e1")
        self._render_validation_rows()

    def _build_info_panel(self, parent: tk.Widget, *, title: str, body_rows: list[tuple[str, tk.StringVar]], row: int = 2) -> None:
        card, body = self._build_auto_card(parent, title)
        card.grid(row=row, column=0, sticky="nsew")
        for idx, (label, var) in enumerate(body_rows):
            tk.Label(body, text=label, bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 8, "bold")).grid(row=idx * 2, column=0, sticky="w", pady=(0 if idx == 0 else 8, 2))
            tk.Label(body, textvariable=var, bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 9), wraplength=320, justify=tk.LEFT).grid(row=idx * 2 + 1, column=0, sticky="w")

    def _build_form_card(self, parent: tk.Widget, row: int, title: str, fields: list[tuple[str, tk.StringVar]], *, columns: int = 1) -> None:
        card, body = self._build_auto_card(parent, title)
        card.grid(row=row, column=0, sticky="ew", pady=(0, SECTION_GAP))
        for col in range(columns):
            body.grid_columnconfigure(col, weight=1)
        for idx, (label, variable) in enumerate(fields):
            col = idx % columns
            block_row = (idx // columns) * 2
            self._build_inline_entry(body, block_row, col, label, variable)

    def _build_targets_card(self, parent: tk.Widget, row: int) -> None:
        card, body = self._build_auto_card(parent, "크롤링 대상")
        card.grid(row=row, column=0, sticky="ew", pady=(0, SECTION_GAP))
        options = [
            ("카테고리 페이지", self.crawling_vars["category_pages"]),
            ("상품 상세 페이지", self.crawling_vars["product_detail_pages"]),
            ("브랜드 페이지", self.crawling_vars["brand_pages"]),
            ("키워드 검색", self.crawling_vars["keyword_search"]),
        ]
        for idx, (label, variable) in enumerate(options):
            self._build_check(body, idx, label, variable)
        self._build_entry_row(body, len(options), "키워드", self.crawling_vars["keyword"])

    def _build_toggle_card(self, parent: tk.Widget, row: int, title: str, fields: list[tuple[str, tk.BooleanVar]]) -> None:
        card, body = self._build_auto_card(parent, title)
        card.grid(row=row, column=0, sticky="ew", pady=(0, SECTION_GAP))
        for idx, (label, variable) in enumerate(fields):
            self._build_switch(body, idx, label, variable)

    def _build_telegram_card(self, parent: tk.Widget, row: int) -> None:
        card, body = self._build_auto_card(parent, "Telegram")
        card.grid(row=row, column=0, sticky="ew", pady=(0, SECTION_GAP))
        self._build_switch(body, 0, "사용 여부", self.notification_vars["telegram_enabled"])
        self._build_entry_row(body, 1, "Bot Token", self.notification_vars["telegram_bot_token"], show="*")
        self._build_entry_row(body, 3, "Chat ID", self.notification_vars["telegram_chat_id"])
        self.controller._mini_button(body, "알림 테스트", lambda: self.controller.dispatch_ui_action("설정: Telegram 테스트", self.test_telegram_notification, category="settings"), "#1e3350", "#294565").grid(row=5, column=0, sticky="e", pady=(8, 0))

    def _build_email_card(self, parent: tk.Widget, row: int) -> None:
        card, body = self._build_auto_card(parent, "이메일 알림")
        card.grid(row=row, column=0, sticky="ew", pady=(0, SECTION_GAP))
        self._build_switch(body, 0, "사용 여부", self.notification_vars["email_enabled"])
        self._build_entry_row(body, 1, "이메일 주소", self.notification_vars["email_address"])
        self._build_entry_row(body, 3, "비밀번호", self.notification_vars["email_password"], show="*")

    def _build_action_only_card(self, parent: tk.Widget, row: int, title: str, buttons: list[tuple[str, object, str, str]]) -> None:
        card, body = self._build_auto_card(parent, title)
        card.grid(row=row, column=0, sticky="ew", pady=(0, SECTION_GAP))
        for idx, (label, callback, bg, active) in enumerate(buttons):
            self.controller._mini_button(body, label, lambda cb=callback: self.controller.dispatch_ui_action(f"설정: {label}", cb, category="settings"), bg, active).grid(row=idx, column=0, sticky="ew", pady=(0, 6 if idx < len(buttons) - 1 else 0))

    def _build_entry_row(self, parent: tk.Widget, row: int, label: str, variable: tk.StringVar, *, button_text: str | None = None, button_command=None, show: str | None = None) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=0)
        tk.Label(parent, text=label, bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 8, "bold")).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0 if row == 0 else 6, 4))
        entry = tk.Entry(parent, textvariable=variable, bg="#091626", fg="#dbeafe", insertbackground="#dbeafe", relief=tk.FLAT, show=show or "")
        entry.grid(row=row + 1, column=0, sticky="ew", ipady=5)
        if button_text and button_command:
            self.controller._mini_button(parent, button_text, button_command, "#1e3350", "#294565").grid(row=row + 1, column=1, sticky="e", padx=(8, 0))

    def _build_inline_entry(self, parent: tk.Widget, row: int, column: int, label: str, variable: tk.StringVar, *, show: str | None = None) -> None:
        wrap = tk.Frame(parent, bg=self.controller.theme["panel"])
        wrap.grid(row=row, column=column, sticky="ew", padx=(0, 8) if column == 0 else (8, 0), pady=(0, 8))
        wrap.grid_columnconfigure(0, weight=1)
        tk.Label(wrap, text=label, bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 4))
        tk.Entry(wrap, textvariable=variable, bg="#091626", fg="#dbeafe", insertbackground="#dbeafe", relief=tk.FLAT, show=show or "").grid(row=1, column=0, sticky="ew", ipady=5)

    def _build_combo_field(self, parent: tk.Widget, row: int, column: int, label: str, variable: tk.StringVar, *, values: list[str]) -> ttk.Combobox:
        wrap = tk.Frame(parent, bg=self.controller.theme["panel"])
        wrap.grid(row=row, column=column, sticky="ew", padx=(0, 8) if column == 0 else (8, 0), pady=(0, 8))
        wrap.grid_columnconfigure(0, weight=1)
        tk.Label(wrap, text=label, bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 4))
        combo = ttk.Combobox(
            wrap,
            textvariable=variable,
            values=[value for value in values if value],
            state="readonly",
            postcommand=self._suspend_scroll_for_dropdown,
        )
        combo.grid(row=1, column=0, sticky="ew")
        combo.bind("<<ComboboxSelected>>", self._resume_scroll_after_dropdown, add="+")
        combo.bind("<FocusOut>", self._resume_scroll_after_dropdown, add="+")
        combo.bind("<Escape>", self._resume_scroll_after_dropdown, add="+")
        combo.bind("<Return>", self._resume_scroll_after_dropdown, add="+")
        return combo

    def _build_check(self, parent: tk.Widget, row: int, label: str, variable: tk.BooleanVar) -> None:
        tk.Checkbutton(parent, text=label, variable=variable, bg=self.controller.theme["panel"], fg="#dbeafe", selectcolor="#102033", activebackground=self.controller.theme["panel"], activeforeground="#ffffff", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=(0, 4))

    def _build_switch(self, parent: tk.Widget, row: int, label: str, variable: tk.BooleanVar) -> None:
        row_frame = tk.Frame(parent, bg=self.controller.theme["panel"])
        row_frame.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        row_frame.grid_columnconfigure(0, weight=1)
        tk.Label(row_frame, text=label, bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
        tk.Checkbutton(row_frame, variable=variable, bg=self.controller.theme["panel"], selectcolor="#102033", activebackground=self.controller.theme["panel"]).grid(row=0, column=1, sticky="e")

    def _build_status_row(self, parent: tk.Widget, row: int, label: str, value_var: tk.StringVar, color_var: tk.StringVar) -> None:
        wrap = tk.Frame(parent, bg=self.controller.theme["panel"])
        wrap.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        wrap.grid_columnconfigure(0, weight=1)
        tk.Label(wrap, text=label, bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
        status = tk.Label(wrap, textvariable=value_var, bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 9))
        status.grid(row=1, column=0, sticky="w", pady=(2, 0))
        def _sync_status_color(*_args, target=status, source=color_var) -> None:
            try:
                if target.winfo_exists():
                    target.configure(fg=source.get())
            except tk.TclError:
                # Widget already destroyed during tab/page rerender.
                return

        color_var.trace_add("write", _sync_status_color)

    def _bind_live_validation(self) -> None:
        for variable in self._iter_all_vars():
            try:
                variable.trace_add("write", self._schedule_live_validation)
            except Exception:
                pass

    def _iter_all_vars(self):
        yield self.spreadsheet_id_var
        yield self.service_account_path_var
        yield self.images_dir_var
        yield self.log_dir_var
        yield self.thumbnail_footer_suffix_var
        yield self.buyma_email_var
        yield self.buyma_password_var
        for variable in self.general_tab_vars.values():
            yield variable
        for bucket in (self.crawling_vars, self.upload_vars, self.notification_vars, self.advanced_vars):
            for variable in bucket.values():
                yield variable

    def _schedule_live_validation(self, *_args) -> None:
        if self.validation_after_id:
            try:
                self.after_cancel(self.validation_after_id)
            except Exception:
                pass
        self.validation_after_id = self.after(350, self._run_live_validation)

    def _run_live_validation(self) -> None:
        self.validation_after_id = None
        issues = self._validate_inputs(full=False)
        if issues:
            self.validation_summary_var.set(issues[0])
        else:
            self.validation_summary_var.set("입력값 기본 검증 통과. 저장 또는 적용할 수 있습니다.")
        current = self._collect_config_payload()
        self.diff_hint_var.set("저장 전 변경사항을 확인할 수 있습니다." if current != self.last_saved_config else "저장된 설정과 동일합니다.")

    def _config_path(self) -> str:
        return get_profile_config_path(self.controller.profile_name)

    def _load_config_into_vars(self) -> None:
        config = load_config(self.controller.profile_name, create_if_missing=True)
        self.last_saved_config = deepcopy(config)
        self.profile_display_var.set(self.controller.profile_name)
        self.config_path_var.set(self._config_path())
        self.last_saved_var.set(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        spreadsheet = config.get("spreadsheet") or {}
        paths = config.get("paths") or {}
        buyma = config.get("buyma") or {}
        tabs = spreadsheet.get("tabs") or {}
        crawling = config.get("crawling") or {}
        upload = config.get("upload") or {}
        notification = config.get("notification") or {}
        advanced = config.get("advanced") or {}

        self.spreadsheet_id_var.set(str(spreadsheet.get("id") or "").strip())
        self.service_account_path_var.set(str(spreadsheet.get("credentials_path") or "").strip() or self.controller._get_available_credentials_path())
        for key, _label in self.GENERAL_TAB_FIELDS:
            self.general_tab_vars[key].set(str(tabs.get(key) or "").strip())
        self.images_dir_var.set(str(paths.get("images_dir") or "").strip() or self.controller._get_configured_images_dir())
        self.log_dir_var.set(str(paths.get("log_dir") or "").strip() or os.path.join(self.controller.data_dir, "logs"))
        footer_suffix = str(paths.get("thumbnail_footer_suffix") or "").strip()
        if not footer_suffix:
            legacy_cfg = self.controller._load_sheet_config()
            footer_suffix = str((legacy_cfg or {}).get("thumbnail_footer_suffix") or "").strip()
        self.thumbnail_footer_suffix_var.set(footer_suffix)
        self.buyma_email_var.set(str(buyma.get("email") or "").strip() or self.controller.buyma_credentials.load_email())
        self.buyma_password_var.set("")

        crawl_base = crawling.get("base") or {}
        crawl_targets = crawling.get("targets") or {}
        crawl_filters = crawling.get("filters") or {}
        crawl_options = crawling.get("options") or {}
        self._set_var(self.crawling_vars["max_pages"], crawl_base.get("max_pages", 5))
        self._set_var(self.crawling_vars["delay_seconds"], crawl_base.get("delay_seconds", 3))
        self._set_var(self.crawling_vars["retry_count"], crawl_base.get("retry_count", 3))
        self._set_var(self.crawling_vars["timeout"], crawl_base.get("timeout", 30))
        self._set_bool(self.crawling_vars["category_pages"], crawl_targets.get("category_pages", True))
        self._set_bool(self.crawling_vars["product_detail_pages"], crawl_targets.get("product_detail_pages", True))
        self._set_bool(self.crawling_vars["brand_pages"], crawl_targets.get("brand_pages", False))
        self._set_bool(self.crawling_vars["keyword_search"], crawl_targets.get("keyword_search", False))
        self._set_var(self.crawling_vars["keyword"], crawl_targets.get("keyword", ""))
        self._set_var(self.crawling_vars["min_price"], crawl_filters.get("min_price", 0))
        self._set_var(self.crawling_vars["max_price"], crawl_filters.get("max_price", 10000000))
        self._set_var(self.crawling_vars["min_reviews"], crawl_filters.get("min_reviews", 0))
        self._set_var(self.crawling_vars["min_sales"], crawl_filters.get("min_sales", 0))
        self._set_bool(self.crawling_vars["download_images"], crawl_options.get("download_images", True))
        self._set_bool(self.crawling_vars["generate_thumbnails"], crawl_options.get("generate_thumbnails", True))
        self._set_bool(self.crawling_vars["save_html"], crawl_options.get("save_html", False))
        self._set_bool(self.crawling_vars["dedupe"], crawl_options.get("dedupe", True))

        upload_base = upload.get("base") or {}
        upload_mapping = upload.get("category_mapping") or {}
        upload_price = upload.get("price") or {}
        upload_options = upload.get("options") or {}
        self._set_var(self.upload_vars["batch_size"], upload_base.get("batch_size", 1))
        self._set_var(self.upload_vars["max_workers"], upload_base.get("max_workers", 1))
        self._set_var(self.upload_vars["retry_count"], upload_base.get("retry_count", 3))
        self._set_var(self.upload_vars["source_category"], upload_mapping.get("source_category", ""))
        self._set_var(self.upload_vars["target_buyma_category"], upload_mapping.get("target_buyma_category", ""))
        self._set_var(self.upload_vars["markup_percent"], upload_price.get("markup_percent", 0))
        self._set_var(self.upload_vars["minimum_margin"], upload_price.get("minimum_margin", 0))
        self._set_var(self.upload_vars["rounding_rule"], upload_price.get("rounding_rule", "100엔"))
        self._set_bool(self.upload_vars["validate_before_upload"], upload_options.get("validate_before_upload", True))
        self._set_bool(self.upload_vars["retry_failed"], upload_options.get("retry_failed", True))
        self._set_bool(self.upload_vars["save_logs"], upload_options.get("save_logs", True))
        self._set_bool(self.upload_vars["auto_price"], upload_options.get("auto_price", True))

        notify_telegram = notification.get("telegram") or {}
        notify_events = notification.get("events") or {}
        notify_email = notification.get("email") or {}
        notify_schedule = notification.get("schedule") or {}
        self._set_bool(self.notification_vars["telegram_enabled"], notify_telegram.get("enabled", False))
        legacy_token = str(notify_telegram.get("bot_token") or "").strip()
        if legacy_token:
            self.controller.telegram_token_store.save(legacy_token)
        self._set_var(self.notification_vars["telegram_bot_token"], self.controller.telegram_token_store.load() or legacy_token)
        self._set_var(self.notification_vars["telegram_chat_id"], notify_telegram.get("chat_id", ""))
        self._set_bool(self.notification_vars["notify_start"], notify_events.get("job_start", True))
        self._set_bool(self.notification_vars["notify_complete"], notify_events.get("job_complete", True))
        self._set_bool(self.notification_vars["notify_error"], notify_events.get("job_error", True))
        self._set_bool(self.notification_vars["notify_important"], notify_events.get("important_only", False))
        self._set_bool(self.notification_vars["email_enabled"], notify_email.get("enabled", False))
        self._set_var(self.notification_vars["email_address"], notify_email.get("address", ""))
        self._set_var(self.notification_vars["email_password"], notify_email.get("password", ""))
        self._set_var(self.notification_vars["schedule_start"], notify_schedule.get("start_time", "09:00"))
        self._set_var(self.notification_vars["schedule_end"], notify_schedule.get("end_time", "22:00"))
        self._set_var(self.notification_vars["schedule_timezone"], notify_schedule.get("timezone", "Asia/Seoul"))

        adv_paths = advanced.get("system_paths") or {}
        adv_exec = advanced.get("execution") or {}
        adv_flags = advanced.get("feature_flags") or {}
        self._set_var(self.advanced_vars["python_path"], adv_paths.get("python_path", ""))
        self._set_var(self.advanced_vars["chrome_path"], adv_paths.get("chrome_path", ""))
        self._set_var(self.advanced_vars["execution_max_workers"], adv_exec.get("max_workers", 1))
        self._set_var(self.advanced_vars["cpu_limit"], adv_exec.get("cpu_limit", 80))
        self._set_var(self.advanced_vars["memory_limit"], adv_exec.get("memory_limit", 2048))
        self._set_bool(self.advanced_vars["async_mode"], adv_flags.get("async_mode", False))
        self._set_bool(self.advanced_vars["smart_retry"], adv_flags.get("smart_retry", True))
        self._set_bool(self.advanced_vars["ai_category"], adv_flags.get("ai_category", False))

        self.available_sheet_tabs = [value.get().strip() for value in self.general_tab_vars.values() if value.get().strip()]
        self._sheet_tabs_auto_loaded = False
        self._set_pending_statuses()
        self._run_live_validation()

    def _set_var(self, variable: tk.StringVar, value: object) -> None:
        variable.set("" if value is None else str(value))

    def _set_bool(self, variable: tk.BooleanVar, value: object) -> None:
        variable.set(bool(value))

    def _get_telegram_bot_token(self) -> str:
        return self.notification_vars["telegram_bot_token"].get().strip() or self.controller.telegram_token_store.load()

    def _set_pending_statuses(self) -> None:
        muted = self.controller.theme["muted"]
        self.connection_color_var.set(muted)
        self.permission_color_var.set(muted)
        self.tabs_color_var.set(muted)
        self.connection_status_var.set("⚠ 연결 테스트 전")
        self.permission_status_var.set("⚠ 권한 확인 전")
        self.tabs_status_var.set("⚠ 시트 탭 확인 전")
        self.sheet_validation_rows = [(self.general_tab_vars[key].get().strip() or key, "대기", "-", "-", "") for key, _label in self.GENERAL_TAB_FIELDS]
        self._render_validation_rows()

    def _collect_config_payload(self) -> dict:
        current = deepcopy(self.last_saved_config or load_config(self.controller.profile_name, create_if_missing=True))
        spreadsheet = current.setdefault("spreadsheet", {})
        spreadsheet["id"] = self.controller._normalize_spreadsheet_id(self.spreadsheet_id_var.get())
        spreadsheet["credentials_path"] = self.service_account_path_var.get().strip()
        tabs = spreadsheet.setdefault("tabs", {})
        for key, _label in self.GENERAL_TAB_FIELDS:
            tabs[key] = self.general_tab_vars[key].get().strip()

        current.setdefault("paths", {}).update(
            {
                "images_dir": self.images_dir_var.get().strip(),
                "log_dir": self.log_dir_var.get().strip(),
                "thumbnail_footer_suffix": self.thumbnail_footer_suffix_var.get().strip(),
            }
        )
        current.setdefault("buyma", {}).update({"email": self.buyma_email_var.get().strip()})

        current["crawling"] = {
            "base": {
                "max_pages": self._as_int(self.crawling_vars["max_pages"], 5),
                "delay_seconds": self._as_int(self.crawling_vars["delay_seconds"], 3),
                "retry_count": self._as_int(self.crawling_vars["retry_count"], 3),
                "timeout": self._as_int(self.crawling_vars["timeout"], 30),
            },
            "targets": {
                "category_pages": self.crawling_vars["category_pages"].get(),
                "product_detail_pages": self.crawling_vars["product_detail_pages"].get(),
                "brand_pages": self.crawling_vars["brand_pages"].get(),
                "keyword_search": self.crawling_vars["keyword_search"].get(),
                "keyword": self.crawling_vars["keyword"].get().strip(),
            },
            "filters": {
                "min_price": self._as_int(self.crawling_vars["min_price"], 0),
                "max_price": self._as_int(self.crawling_vars["max_price"], 10000000),
                "min_reviews": self._as_int(self.crawling_vars["min_reviews"], 0),
                "min_sales": self._as_int(self.crawling_vars["min_sales"], 0),
            },
            "options": {
                "download_images": self.crawling_vars["download_images"].get(),
                "generate_thumbnails": self.crawling_vars["generate_thumbnails"].get(),
                "save_html": self.crawling_vars["save_html"].get(),
                "dedupe": self.crawling_vars["dedupe"].get(),
            },
        }

        current["upload"] = {
            "base": {
                "batch_size": self._as_int(self.upload_vars["batch_size"], 1),
                "max_workers": self._as_int(self.upload_vars["max_workers"], 1),
                "retry_count": self._as_int(self.upload_vars["retry_count"], 3),
            },
            "category_mapping": {
                "source_category": self.upload_vars["source_category"].get().strip(),
                "target_buyma_category": self.upload_vars["target_buyma_category"].get().strip(),
            },
            "price": {
                "markup_percent": self._as_int(self.upload_vars["markup_percent"], 0),
                "minimum_margin": self._as_int(self.upload_vars["minimum_margin"], 0),
                "rounding_rule": self.upload_vars["rounding_rule"].get().strip(),
            },
            "options": {
                "validate_before_upload": self.upload_vars["validate_before_upload"].get(),
                "retry_failed": self.upload_vars["retry_failed"].get(),
                "save_logs": self.upload_vars["save_logs"].get(),
                "auto_price": self.upload_vars["auto_price"].get(),
            },
        }

        current["notification"] = {
            "telegram": {
                "enabled": self.notification_vars["telegram_enabled"].get(),
                "chat_id": self.notification_vars["telegram_chat_id"].get().strip(),
            },
            "events": {
                "job_start": self.notification_vars["notify_start"].get(),
                "job_complete": self.notification_vars["notify_complete"].get(),
                "job_error": self.notification_vars["notify_error"].get(),
                "important_only": self.notification_vars["notify_important"].get(),
            },
            "email": {
                "enabled": self.notification_vars["email_enabled"].get(),
                "address": self.notification_vars["email_address"].get().strip(),
                "password": self.notification_vars["email_password"].get(),
            },
            "schedule": {
                "start_time": self.notification_vars["schedule_start"].get().strip(),
                "end_time": self.notification_vars["schedule_end"].get().strip(),
                "timezone": self.notification_vars["schedule_timezone"].get().strip(),
            },
        }

        current["advanced"] = {
            "system_paths": {
                "python_path": self.advanced_vars["python_path"].get().strip(),
                "chrome_path": self.advanced_vars["chrome_path"].get().strip(),
            },
            "execution": {
                "max_workers": self._as_int(self.advanced_vars["execution_max_workers"], 1),
                "cpu_limit": self._as_int(self.advanced_vars["cpu_limit"], 80),
                "memory_limit": self._as_int(self.advanced_vars["memory_limit"], 2048),
            },
            "feature_flags": {
                "async_mode": self.advanced_vars["async_mode"].get(),
                "smart_retry": self.advanced_vars["smart_retry"].get(),
                "ai_category": self.advanced_vars["ai_category"].get(),
            },
        }
        return current

    def _validate_inputs(self, *, full: bool) -> list[str]:
        issues: list[str] = []
        spreadsheet_id = self.controller._normalize_spreadsheet_id(self.spreadsheet_id_var.get())
        if not self.controller._is_valid_spreadsheet_id(spreadsheet_id):
            issues.append("Spreadsheet ID가 비어 있거나 형식이 올바르지 않습니다.")
        service_path = self.service_account_path_var.get().strip()
        if service_path and not os.path.isfile(os.path.abspath(os.path.expanduser(service_path))):
            issues.append("서비스 계정 JSON 경로를 확인해 주세요.")
        for key, label in self.GENERAL_TAB_FIELDS:
            if not self.general_tab_vars[key].get().strip():
                issues.append(f"{label} 값을 입력해 주세요.")
        for label, raw in (("images_dir", self.images_dir_var.get()), ("log_dir", self.log_dir_var.get())):
            path = os.path.abspath(os.path.expanduser(raw.strip()))
            if not path:
                issues.append(f"{label}를 입력해 주세요.")
                continue
            try:
                os.makedirs(path, exist_ok=True)
            except Exception as exc:
                issues.append(f"{label}를 준비할 수 없습니다: {exc}")
        if full:
            numeric_checks = [
                ("크롤링 최대 페이지", self.crawling_vars["max_pages"]),
                ("크롤링 지연", self.crawling_vars["delay_seconds"]),
                ("업로드 배치 크기", self.upload_vars["batch_size"]),
                ("업로드 워커 수", self.upload_vars["max_workers"]),
                ("CPU 제한", self.advanced_vars["cpu_limit"]),
                ("메모리 제한", self.advanced_vars["memory_limit"]),
            ]
            for label, var in numeric_checks:
                if self._invalid_int(var):
                    issues.append(f"{label}는 숫자여야 합니다.")
            if self.notification_vars["telegram_enabled"].get():
                if not self._get_telegram_bot_token():
                    issues.append("Telegram을 쓰려면 Bot Token이 필요합니다.")
                if not self.notification_vars["telegram_chat_id"].get().strip():
                    issues.append("Telegram을 쓰려면 Chat ID가 필요합니다.")
        entered_email = self.buyma_email_var.get().strip()
        entered_password = self.buyma_password_var.get().strip()
        if entered_password and not entered_email:
            issues.append("BUYMA 비밀번호를 입력했다면 이메일도 함께 입력해 주세요.")
        return issues

    def _as_int(self, var: tk.StringVar, default: int) -> int:
        try:
            return int(str(var.get()).strip())
        except Exception:
            return default

    def _invalid_int(self, var: tk.StringVar) -> bool:
        try:
            int(str(var.get()).strip())
            return False
        except Exception:
            return True

    def load_google_sheet_tabs(self, *, silent: bool = False) -> bool:
        issues = self._validate_inputs(full=False)
        if issues:
            self.validation_summary_var.set(issues[0])
            self.connection_color_var.set(self.controller.theme["red"])
            return False
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build

            credentials_path = os.path.abspath(os.path.expanduser(self.service_account_path_var.get().strip()))
            creds = Credentials.from_service_account_file(credentials_path, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
            service = build("sheets", "v4", credentials=creds)
            spreadsheet = service.spreadsheets().get(spreadsheetId=self.controller._normalize_spreadsheet_id(self.spreadsheet_id_var.get())).execute()
            sheets = spreadsheet.get("sheets", [])
            self.available_sheet_tabs = [str(item.get("properties", {}).get("title") or "").strip() for item in sheets if str(item.get("properties", {}).get("title") or "").strip()]
            self._update_sheet_combobox_values()
            self.connection_color_var.set(self.controller.theme["green"])
            self.connection_status_var.set("✔ 탭 목록 로드 성공")
            self.validation_summary_var.set(f"{len(self.available_sheet_tabs)}개 탭을 불러왔습니다.")
            return True
        except Exception as exc:
            self.connection_color_var.set(self.controller.theme["red"])
            self.connection_status_var.set("✖ 탭 목록 로드 실패")
            self.validation_summary_var.set(f"탭 목록 로드 실패: {exc}")
            if not silent:
                messagebox.showerror("탭 목록 불러오기 실패", f"Google Sheets 탭 목록을 불러오지 못했습니다.\n\n{exc}")
            return False

    def test_google_sheet_connection(self, *, silent: bool = False) -> bool:
        issues = self._validate_inputs(full=False)
        if issues:
            self.validation_summary_var.set(issues[0])
            self.connection_color_var.set(self.controller.theme["red"])
            return False
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build

            credentials_path = os.path.abspath(os.path.expanduser(self.service_account_path_var.get().strip()))
            creds = Credentials.from_service_account_file(credentials_path, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
            service = build("sheets", "v4", credentials=creds)
            spreadsheet = service.spreadsheets().get(spreadsheetId=self.controller._normalize_spreadsheet_id(self.spreadsheet_id_var.get())).execute()
            sheets = spreadsheet.get("sheets", [])
            by_title = {str(item.get("properties", {}).get("title") or "").strip(): item for item in sheets}
            self.available_sheet_tabs = list(by_title.keys())
            self._update_sheet_combobox_values()

            self.connection_color_var.set(self.controller.theme["green"])
            self.permission_color_var.set(self.controller.theme["green"])
            self.connection_status_var.set("✔ 연결 성공")
            self.permission_status_var.set("✔ 읽기 권한 확인됨")

            rows: list[tuple[str, str, str, str, str]] = []
            missing: list[str] = []
            for key, _label in self.GENERAL_TAB_FIELDS:
                name = self.general_tab_vars[key].get().strip()
                sheet = by_title.get(name)
                if sheet is None:
                    missing.append(name)
                    rows.append((name or key, "누락", "-", "-", "필수"))
                    continue
                grid = sheet.get("properties", {}).get("gridProperties", {})
                rows.append((name, "정상", str(grid.get("rowCount", "-")), str(grid.get("columnCount", "-")), ""))
            self.sheet_validation_rows = rows
            self._render_validation_rows()

            if missing:
                self.tabs_color_var.set(self.controller.theme["red"])
                self.tabs_status_var.set(f"✖ 누락 {len(missing)}개")
                self.validation_summary_var.set(f"누락된 탭: {', '.join(missing)}")
                return False
            self.tabs_color_var.set(self.controller.theme["green"])
            self.tabs_status_var.set("✔ 모든 필수 탭 정상")
            self.validation_summary_var.set("Google Sheets 연결과 필수 탭 검증이 완료되었습니다.")
            return True
        except Exception as exc:
            self.connection_color_var.set(self.controller.theme["red"])
            self.permission_color_var.set(self.controller.theme["red"])
            self.tabs_color_var.set(self.controller.theme["red"])
            self.connection_status_var.set("✖ 연결 실패")
            self.permission_status_var.set("✖ 권한 확인 실패")
            self.tabs_status_var.set("✖ 검증 중단")
            self.validation_summary_var.set(f"Google Sheets 연결 실패: {exc}")
            self.sheet_validation_rows = [(self.general_tab_vars[key].get().strip() or key, "오류", "-", "-", "") for key, _label in self.GENERAL_TAB_FIELDS]
            self._render_validation_rows()
            if not silent:
                messagebox.showerror("연결 실패", f"Google Sheets 연결 확인에 실패했습니다.\n\n{exc}")
            return False

    def test_buyma_credentials(self) -> bool:
        email = self.buyma_email_var.get().strip() or self.controller.buyma_credentials.load_email().strip()
        password = self.buyma_password_var.get().strip()
        if not email or "@" not in email:
            self.buyma_status_var.set("이메일 형식 확인 필요")
            messagebox.showwarning("BUYMA 계정 확인", "유효한 BUYMA 이메일을 입력해 주세요.")
            return False
        if not password and email != self.controller.buyma_credentials.load_email().strip():
            self.buyma_status_var.set("비밀번호 필요")
            messagebox.showwarning("BUYMA 계정 확인", "새 이메일을 저장하려면 비밀번호도 함께 입력해 주세요.")
            return False
        self.buyma_status_var.set("계정 형식 확인 완료")
        messagebox.showinfo("BUYMA 계정 확인", "BUYMA 계정 입력 형식이 정상입니다.")
        return True

    def test_telegram_notification(self) -> bool:
        if not self.notification_vars["telegram_enabled"].get():
            self.telegram_status_var.set("비활성")
            messagebox.showwarning("Telegram 테스트", "Telegram 알림이 비활성화되어 있습니다.")
            return False
        token = self._get_telegram_bot_token()
        chat_id = self.notification_vars["telegram_chat_id"].get().strip()
        if not token or not chat_id:
            self.telegram_status_var.set("토큰/채팅 ID 필요")
            messagebox.showwarning("Telegram 테스트", "Bot Token과 Chat ID를 입력해 주세요.")
            return False
        try:
            url = (
                "https://api.telegram.org/bot"
                + token
                + "/sendMessage?"
                + urllib.parse.urlencode({"chat_id": chat_id, "text": "[Auto Shop] 설정 테스트 메시지입니다."})
            )
            request = urllib.request.Request(url, method="POST")
            with urllib.request.urlopen(request, timeout=10, context=ssl.create_default_context()) as response:
                payload = json.loads(response.read().decode("utf-8", "replace"))
            if not payload.get("ok"):
                raise RuntimeError(str(payload))
            self.controller.telegram_token_store.save(token)
            self.telegram_status_var.set("전송 성공")
            messagebox.showinfo("Telegram 테스트", "테스트 메시지를 전송했습니다.")
            return True
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            try:
                payload = json.loads(detail)
                detail = str(payload.get("description") or detail)
            except Exception:
                pass
            self.telegram_status_var.set("전송 실패")
            messagebox.showerror("Telegram 테스트 실패", f"테스트 메시지를 보내지 못했습니다.\n\nHTTP {exc.code}: {detail}")
            return False
        except Exception as exc:
            self.telegram_status_var.set("전송 실패")
            messagebox.showerror("Telegram 테스트 실패", f"테스트 메시지를 보내지 못했습니다.\n\n{exc}")
            return False

    def show_config_diff(self) -> bool:
        current = self._collect_config_payload()
        before = json.dumps(self.last_saved_config or {}, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
        after = json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
        diff_lines = list(difflib.unified_diff(before, after, fromfile="saved", tofile="current", lineterm=""))
        if not diff_lines:
            messagebox.showinfo("변경사항 보기", "저장된 설정과 현재 입력값이 같습니다.")
            return True
        viewer = tk.Toplevel(self)
        viewer.title("설정 변경사항")
        viewer.geometry("960x640")
        viewer.configure(bg=self.controller.theme["bg"])
        text = ScrolledText(viewer, wrap=tk.NONE, bg="#081322", fg="#dbeafe", insertbackground="#dbeafe", font=("Consolas", 10))
        text.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        text.insert("1.0", "\n".join(diff_lines))
        text.configure(state=tk.DISABLED)
        return True

    def save_current_config(self, *, show_message: bool = True) -> bool:
        issues = self._validate_inputs(full=True)
        if issues:
            self.validation_summary_var.set(issues[0])
            messagebox.showwarning("입력 확인", "\n".join(issues))
            return False

        config = self._collect_config_payload()
        try:
            credentials_path = self.service_account_path_var.get().strip()
            if credentials_path and os.path.isfile(os.path.abspath(os.path.expanduser(credentials_path))):
                os.makedirs(self.controller.data_dir, exist_ok=True)
                source_path = os.path.abspath(os.path.expanduser(credentials_path))
                target_path = self.controller._get_credentials_target_path()
                if not _same_file(source_path, target_path):
                    shutil.copy2(source_path, target_path)

            email = self.buyma_email_var.get().strip()
            password = self.buyma_password_var.get().strip()
            if email and password:
                self.controller.buyma_credentials.save(email, password)

            telegram_token = self.notification_vars["telegram_bot_token"].get().strip()
            if telegram_token:
                self.controller.telegram_token_store.save(telegram_token)
            elif not self.notification_vars["telegram_enabled"].get():
                self.controller.telegram_token_store.delete()

            config_path = save_config(self.controller.profile_name, config)
        except Exception as exc:
            self.validation_summary_var.set(f"설정 저장 실패(config.json): {exc}")
            messagebox.showerror("저장 실패", f"config.json 저장에 실패했습니다.\n\n{exc}")
            return False

        try:
            self.controller.profile_config = deepcopy(config)
            self.last_saved_config = deepcopy(config)
            self.buyma_password_var.set("")
            self.last_saved_var.set(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            self.config_path_var.set(config_path)
            self.diff_hint_var.set("저장된 설정과 동일합니다.")

            legacy = self.controller._load_sheet_config()
            legacy.update(
                {
                    "spreadsheet_id": config["spreadsheet"]["id"],
                    "sheet_name": config["spreadsheet"]["tabs"]["product_input"],
                    "category_sheet_name": config["spreadsheet"]["tabs"]["category"],
                    "candidate_sheet_name": config["spreadsheet"]["tabs"]["candidate"],
                    "queue_sheet_name": config["spreadsheet"]["tabs"]["scout_queue"],
                    "log_sheet_name": config["spreadsheet"]["tabs"]["log"],
                    "category_mapping_candidates_sheet_name": config["spreadsheet"]["tabs"]["category_mapping_candidates"],
                    "images_dir": config["paths"]["images_dir"],
                    "log_dir": config["paths"]["log_dir"],
                    "thumbnail_footer_suffix": config["paths"].get("thumbnail_footer_suffix", ""),
                    "credentials_path": config["spreadsheet"].get("credentials_path", ""),
                }
            )
            if not self.controller._save_sheet_config(legacy):
                self.validation_summary_var.set("설정 저장 실패(sheets_config.json)")
                return False
            self.test_google_sheet_connection(silent=True)
            self.controller.refresh_first_run_wizard()
            self.controller._refresh_system_status_labels()
            self.validation_summary_var.set("설정을 저장했습니다. 일부 옵션은 다음 작업부터 반영됩니다.")
            if show_message:
                messagebox.showinfo("설정 저장", f"설정을 저장했습니다.\n{config_path}")
            return True
        except Exception as exc:
            self.validation_summary_var.set(f"설정 적용 후처리 실패: {exc}")
            messagebox.showerror("저장 실패", f"설정 후처리 중 오류가 발생했습니다.\n\n{exc}")
            return False

    def apply_config(self) -> bool:
        if not self.save_current_config(show_message=False):
            return False
        self.controller.profile_config = load_config(self.controller.profile_name, create_if_missing=True)
        self.controller.refresh_first_run_wizard()
        self.controller._refresh_system_status_labels()
        self.validation_summary_var.set("설정을 적용했습니다. 일부 변경은 다음 실행부터 완전히 반영됩니다.")
        messagebox.showinfo("적용 완료", "설정을 현재 런타임에 반영했습니다.")
        return True

    def reset_to_saved_config(self) -> bool:
        self._load_config_into_vars()
        self._render_active_tab()
        return True

    def _clear_runtime_cache(self) -> bool:
        try:
            cache_dir = os.path.join(self.controller.data_dir, "cache")
            if os.path.isdir(cache_dir):
                shutil.rmtree(cache_dir)
            self.validation_summary_var.set("캐시를 삭제했습니다.")
            messagebox.showinfo("캐시 삭제", "런타임 캐시를 정리했습니다.")
            return True
        except Exception as exc:
            messagebox.showerror("캐시 삭제 실패", f"캐시를 정리하지 못했습니다.\n\n{exc}")
            return False

    def _clear_log_files(self) -> bool:
        try:
            logs_dir = self.controller._get_configured_log_dir()
            if os.path.isdir(logs_dir):
                for name in os.listdir(logs_dir):
                    path = os.path.join(logs_dir, name)
                    if os.path.isfile(path):
                        os.remove(path)
            self.validation_summary_var.set("로그 파일을 정리했습니다.")
            messagebox.showinfo("로그 정리", "프로필 로그 파일을 정리했습니다.")
            return True
        except Exception as exc:
            messagebox.showerror("로그 정리 실패", f"로그 파일을 정리하지 못했습니다.\n\n{exc}")
            return False

    def _reset_config_defaults(self) -> bool:
        if not messagebox.askyesno("설정 초기화", "현재 프로필 설정을 기본값으로 되돌릴까요?"):
            return False
        try:
            from config.config_service import default_config

            config = default_config()
            save_config(self.controller.profile_name, config)
            self.last_saved_config = deepcopy(config)
            self._load_config_into_vars()
            self._render_active_tab()
            self.validation_summary_var.set("기본 설정으로 초기화했습니다.")
            return True
        except Exception as exc:
            messagebox.showerror("초기화 실패", f"기본 설정으로 되돌리지 못했습니다.\n\n{exc}")
            return False

    def _choose_service_account_file(self) -> None:
        path = filedialog.askopenfilename(title="서비스 계정 JSON 선택", initialdir=os.path.expanduser("~"), filetypes=[("JSON files", "*.json"), ("All files", "*.*")], parent=self)
        if path:
            self.service_account_path_var.set(os.path.abspath(os.path.expanduser(path)))

    def _choose_directory(self, variable: tk.StringVar) -> None:
        initialdir = variable.get().strip() or os.path.expanduser("~")
        path = filedialog.askdirectory(title="폴더 선택", initialdir=initialdir, mustexist=False, parent=self)
        if path:
            variable.set(os.path.abspath(os.path.expanduser(path)))

    def _render_validation_rows(self) -> None:
        if not hasattr(self, "validation_table") or not self.validation_table.winfo_exists():
            return
        for item in self.validation_table.get_children():
            self.validation_table.delete(item)
        for name, status, row_count, col_count, note in self.sheet_validation_rows:
            tag = "ok" if status == "정상" else "error" if status in {"누락", "오류"} else "pending"
            self.validation_table.insert("", tk.END, values=(name, status, row_count, col_count, note), tags=(tag,))
