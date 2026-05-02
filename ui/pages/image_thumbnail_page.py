from __future__ import annotations

import os
import tkinter as tk
import webbrowser
from dataclasses import dataclass
from tkinter import messagebox, ttk
from typing import Any

from ui.pages.base_page import BasePage, SECTION_GAP, SURFACE_BG
from ui.theme import BOTTOM_TABLE_HEIGHT

try:
    from PIL import Image, ImageTk
except Exception:  # pragma: no cover
    Image = None
    ImageTk = None


def get_latest_preview_images(images_dir: str, limit: int = 6) -> list[dict[str, object]]:
    """
    images_dir 하위를 재귀 탐색하여 이미지 파일을 수집하고
    파일 수정시간(mtime) 내림차순으로 최신 limit개를 반환한다.
    """
    if not images_dir:
        return []

    root = os.path.abspath(os.path.expanduser(images_dir))
    if not os.path.isdir(root):
        return []

    allowed_exts = {".jpg", ".jpeg", ".png", ".webp"}
    excluded_suffixes = (".tmp", ".part", ".crdownload")
    records: list[dict[str, object]] = []

    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            if filename.startswith(".") or filename.startswith("~$"):
                continue
            if filename.lower().endswith(excluded_suffixes):
                continue

            ext = os.path.splitext(filename)[1].lower()
            if ext not in allowed_exts:
                continue

            path = os.path.join(dirpath, filename)
            try:
                mtime = float(os.path.getmtime(path))
            except Exception:
                continue

            records.append(
                {
                    "path": path,
                    "name": os.path.splitext(filename)[0],
                    "mtime": mtime,
                    "folder": os.path.basename(os.path.dirname(path)),
                }
            )

    records.sort(key=lambda item: float(item.get("mtime", 0.0)), reverse=True)
    return records[: max(0, int(limit or 0))]


@dataclass
class _PreviewRow:
    no: str
    name: str
    brand: str
    state: str
    image_paths: str
    mtime: float = 0.0


class ImageThumbnailPage(BasePage):
    PREVIEW_LIMIT = 5
    PREVIEW_COLUMNS = 5
    PREVIEW_CARD_WIDTH = 162
    FAILED_LIMIT = 200
    REFRESH_MS = 1200
    PROGRESS_PANEL_MIN_HEIGHT = 286
    PREVIEW_PANEL_MIN_HEIGHT = 438
    PREVIEW_IMAGE_BOX_HEIGHT = 120
    PREVIEW_TEXT_BOX_HEIGHT = 52

    def __init__(self, parent: tk.Widget, controller) -> None:
        super().__init__(
            parent,
            controller,
            title="이미지 / 썸네일",
            subtitle="이미지 다운로드·썸네일 생성·업로드 대기 상태를 운영 콘솔처럼 모니터링합니다.",
        )
        self._refresh_job: str | None = None
        self._preview_photo_refs: list[object] = []
        self._preview_image_refs: dict[str, object] = {}
        self._image_cache: dict[tuple[str, float, int, int], object] = {}
        self._last_preview_keys: list[tuple[str, float]] = []

        self.downloaded_var = tk.IntVar(value=0)
        self.thumbs_var = tk.IntVar(value=0)
        self.pending_var = tk.IntVar(value=0)
        self.failed_var = tk.IntVar(value=0)
        self.total_var = tk.IntVar(value=0)

        self.progress_ratio_var = tk.DoubleVar(value=0.0)
        self.progress_percent_var = tk.StringVar(value="0%")
        self.progress_done_total_var = tk.StringVar(value="0 / 0")
        self.remaining_var = tk.StringVar(value="0 건")
        self.eta_var = tk.StringVar(value="- 분")
        self.speed_var = tk.StringVar(value="- img/sec")
        self.started_at_var = tk.StringVar(value="-")

        self.status_waiting_var = tk.StringVar(value="0")
        self.status_running_var = tk.StringVar(value="0")
        self.status_done_var = tk.StringVar(value="0")
        self.status_failed_var = tk.StringVar(value="0")

        self.stage_image_var = tk.StringVar(value="0 / 0")
        self.stage_thumb_var = tk.StringVar(value="0 / 0")
        self.stage_upload_var = tk.StringVar(value="0 / 0")

        self.progress_ring: tk.Canvas | None = None
        self.progress_bars: dict[str, ttk.Progressbar] = {}
        self.preview_wrap: tk.Frame | None = None
        self.failed_table: ttk.Treeview | None = None

        self.build()
        self.refresh_view_data(update_preview=True)
        self._schedule_refresh()

    def build(self) -> None:
        self.build_header()
        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_rowconfigure(0, weight=0)
        self.body.grid_rowconfigure(1, weight=0)
        self.body.grid_rowconfigure(2, weight=0)
        self.body.grid_rowconfigure(3, weight=1)
        self._build_top_metrics(row=0)
        self._build_recommended_actions(row=1)
        self._build_mid_panels(row=2)
        self._build_bottom_panels(row=3)

    def refresh_view(self) -> None:
        super().refresh_view()
        self._last_preview_keys = []
        self.refresh_view_data(update_preview=True)

    def _build_top_metrics(self, *, row: int) -> None:
        metrics = [
            ("이미지 다운로드", self.downloaded_var, "이미지 저장 완료 기준", self.controller.theme["blue"]),
            ("썸네일 생성", self.thumbs_var, "썸네일 생성 완료 기준", self.controller.theme["purple"]),
            ("대기 이미지", self.pending_var, "이미지 저장/썸네일 대기", self.controller.theme["yellow"]),
            ("실패 이미지", self.failed_var, "실패·오류 상태", self.controller.theme["red"]),
            ("전체 상품", self.total_var, "시트 내 전체 상품 수", self.controller.theme["green"]),
        ]
        wrap = tk.Frame(self.body, bg=self.controller.theme["bg"])
        wrap.grid(row=row, column=0, sticky="ew", pady=(0, SECTION_GAP))
        for i in range(len(metrics)):
            wrap.grid_columnconfigure(i, weight=1, uniform="img_metrics")
        for idx, (title, var, desc, accent) in enumerate(metrics):
            card = self.controller._panel(wrap, padx=14, pady=12)
            card.grid(row=0, column=idx, sticky="nsew", padx=(0 if idx == 0 else 6, 0 if idx == len(metrics) - 1 else 6))
            tk.Label(card, text=title, bg=self.controller.theme["panel"], fg=accent, font=("Segoe UI", 10, "bold")).pack(anchor="w")
            num_row = tk.Frame(card, bg=self.controller.theme["panel"])
            num_row.pack(anchor="w", pady=(8, 2))
            tk.Label(num_row, textvariable=self._formatted_int_var(var), bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 22, "bold")).pack(side=tk.LEFT)
            tk.Label(num_row, text="건", bg=self.controller.theme["panel"], fg="#cbd5e1", font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT, padx=(4, 0), pady=(6, 0))
            tk.Label(card, text=desc, bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 8)).pack(anchor="w", pady=(4, 0))

    def _build_recommended_actions(self, *, row: int) -> None:
        card, body = self.build_panel_card(self.body, "권장 작업", level="mid", min_height=132)
        card.grid(row=row, column=0, sticky="ew", pady=(0, SECTION_GAP))
        for i in range(4):
            body.grid_columnconfigure(i, weight=1, uniform="rec_actions")
        actions = [
            ("이미지 다운로드 실행", lambda: f"대기 이미지 {self.pending_var.get():,}건 처리", self.controller.theme["blue"], self.controller.theme["blue_2"], self.start_image_download),
            ("썸네일 생성 실행", lambda: f"생성 대기 이미지 {self.pending_var.get():,}건", self.controller.theme["purple"], self.controller.theme["purple"], self.start_thumbnail_generation),
            ("실패 재시도 실행", lambda: f"실패 이미지 {self.failed_var.get():,}건 재시도", "#7f1d1d", "#991b1b", self.retry_failed_images),
            ("자동 처리 시작  추천", lambda: "다운로드 → 썸네일 → 업로드", "#1f2937", "#374151", self.start_auto_pipeline),
        ]
        self._recommended_sub_vars: list[tk.StringVar] = []
        for idx, (title, subtitle_fn, bg, active, handler) in enumerate(actions):
            sub_var = tk.StringVar(value=subtitle_fn())
            self._recommended_sub_vars.append(sub_var)
            btn = self._build_action_tile(body, title=title, subtitle_var=sub_var, bg=bg, active=active, command=handler)
            btn.grid(row=0, column=idx, sticky="nsew", padx=(0 if idx == 0 else 6, 0 if idx == 3 else 6))

    def _build_mid_panels(self, *, row: int) -> None:
        shell = tk.Frame(self.body, bg=self.controller.theme["bg"])
        shell.grid(row=row, column=0, sticky="ew", pady=(0, SECTION_GAP))
        shell.grid_columnconfigure(0, weight=3, uniform="mid_cols")
        shell.grid_columnconfigure(1, weight=2, uniform="mid_cols")
        left_card, left_body = self.build_panel_card(shell, "이미지 진행률", level="mid", min_height=self.PROGRESS_PANEL_MIN_HEIGHT)
        left_card.grid(row=0, column=0, sticky="nsew", padx=(0, SECTION_GAP // 2))
        right_card, right_body = self.build_panel_card(shell, "작업 / 상태 현황", level="mid", min_height=self.PROGRESS_PANEL_MIN_HEIGHT)
        right_card.grid(row=0, column=1, sticky="nsew", padx=(SECTION_GAP // 2, 0))
        self._build_progress_panel(left_body)
        self._build_status_panel(right_body)

    def _build_bottom_panels(self, *, row: int) -> None:
        shell = tk.Frame(self.body, bg=self.controller.theme["bg"])
        shell.grid(row=row, column=0, sticky="nsew")
        shell.grid_columnconfigure(0, weight=3, uniform="bottom_cols")
        shell.grid_columnconfigure(1, weight=2, uniform="bottom_cols")
        shell.grid_rowconfigure(0, weight=1)

        preview_card, preview_body = self.build_panel_card(shell, "이미지 미리보기 (최근 저장순)", level="bottom", min_height=self.PREVIEW_PANEL_MIN_HEIGHT)
        preview_card.grid(row=0, column=0, sticky="nsew", padx=(0, SECTION_GAP // 2))
        preview_body.grid_columnconfigure(0, weight=1)
        preview_body.grid_rowconfigure(0, weight=1)
        self.preview_wrap = tk.Frame(preview_body, bg=self.controller.theme["panel"])
        self.preview_wrap.grid(row=0, column=0, sticky="nsew")

        table_wrap = tk.Frame(shell, bg=self.controller.theme["bg"])
        table_wrap.grid(row=0, column=1, sticky="nsew", padx=(SECTION_GAP // 2, 0))
        table_wrap.grid_columnconfigure(0, weight=1)
        table_wrap.grid_rowconfigure(0, weight=1)
        failed_card, table = self.build_simple_table(
            table_wrap,
            "실패 이미지 목록",
            [("no", "No.", 58), ("name", "상품명", 220), ("brand", "브랜드", 100), ("reason", "실패 사유", 130), ("time", "시간", 86)],
            [],
            level="bottom",
            min_height=BOTTOM_TABLE_HEIGHT,
            empty_message="실패 이미지가 없습니다.",
            empty_action=self.get_empty_table_action("image"),
        )
        failed_card.grid(row=0, column=0, sticky="nsew")
        self.failed_table = table

        action_row = tk.Frame(failed_card, bg=self.controller.theme["panel"])
        action_row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        action_row.grid_columnconfigure(0, weight=1)
        self.controller._mini_button(action_row, "선택 항목 재시도", self.retry_selected_failed_rows, "#7f1d1d", "#991b1b").grid(row=0, column=1, sticky="e")

    def _build_action_tile(self, parent: tk.Widget, *, title: str, subtitle_var: tk.StringVar, bg: str, active: str, command) -> tk.Frame:
        frame = tk.Frame(parent, bg=bg, cursor="hand2", padx=12, pady=10, highlightthickness=1, highlightbackground="#334155")
        title_lbl = tk.Label(frame, text=title, bg=bg, fg="#ffffff", font=("Segoe UI", 12, "bold"), anchor="w")
        sub_lbl = tk.Label(frame, textvariable=subtitle_var, bg=bg, fg="#dbeafe", font=("Segoe UI", 10), anchor="w")
        title_lbl.pack(anchor="w")
        sub_lbl.pack(anchor="w", pady=(6, 0))
        for w in (frame, title_lbl, sub_lbl):
            w.bind("<Enter>", lambda _e: (frame.configure(bg=active), title_lbl.configure(bg=active), sub_lbl.configure(bg=active)))
            w.bind("<Leave>", lambda _e: (frame.configure(bg=bg), title_lbl.configure(bg=bg), sub_lbl.configure(bg=bg)))
            w.bind("<Button-1>", lambda _e: command())
        return frame

    def _build_progress_panel(self, parent: tk.Widget) -> None:
        parent.grid_columnconfigure(0, weight=0)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(2, weight=0)
        self.progress_ring = tk.Canvas(parent, width=132, height=132, bg=self.controller.theme["panel"], highlightthickness=0)
        self.progress_ring.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 14))

        right = tk.Frame(parent, bg=self.controller.theme["panel"])
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(1, weight=1)
        stats = [
            ("완료 / 전체", self.progress_done_total_var),
            ("남은 이미지", self.remaining_var),
            ("예상 남은 시간", self.eta_var),
            ("현재 처리 속도", self.speed_var),
            ("시작 시간", self.started_at_var),
        ]
        for idx, (label, var) in enumerate(stats):
            tk.Label(right, text=label, bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 9, "bold")).grid(row=idx, column=0, sticky="w", pady=(0, 4))
            tk.Label(right, textvariable=var, bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 11, "bold")).grid(row=idx, column=1, sticky="e", pady=(0, 4))

        stage = tk.Frame(parent, bg=self.controller.theme["panel"])
        stage.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        for i in range(3):
            stage.grid_columnconfigure(i, weight=1, uniform="stage_cols")
        self._build_stage_tile(stage, 0, "이미지 저장", self.stage_image_var, self.controller.theme["blue"])
        self._build_stage_tile(stage, 1, "썸네일 생성", self.stage_thumb_var, self.controller.theme["purple"])
        self._build_stage_tile(stage, 2, "업로드 대기", self.stage_upload_var, self.controller.theme["yellow"])

    def _build_stage_tile(self, parent: tk.Widget, col: int, title: str, value_var: tk.StringVar, color: str) -> None:
        tile = tk.Frame(parent, bg=SURFACE_BG, padx=10, pady=8, highlightbackground=self.controller.theme["line"], highlightthickness=1)
        tile.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 4, 0 if col == 2 else 4))
        tk.Label(tile, text=title, bg=SURFACE_BG, fg=color, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        tk.Label(tile, textvariable=value_var, bg=SURFACE_BG, fg=self.controller.theme["text"], font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(4, 0))

    def _build_status_panel(self, parent: tk.Widget) -> None:
        rows = [
            ("이미지 저장", self.controller.theme["blue"], self.stage_image_var),
            ("썸네일 생성", self.controller.theme["purple"], self.stage_thumb_var),
            ("업로드 대기", self.controller.theme["yellow"], self.stage_upload_var),
        ]
        self.progress_bars = {}
        for idx, (label, color, value_var) in enumerate(rows):
            wrap = tk.Frame(parent, bg=self.controller.theme["panel"])
            wrap.grid(row=idx, column=0, sticky="ew", pady=(0, 8))
            wrap.grid_columnconfigure(1, weight=1)
            tk.Label(wrap, text=label, bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 8))
            style_name = f"Ops.{label}.Horizontal.TProgressbar"
            ttk.Style().configure(style_name, troughcolor="#1f2e43", background=color, bordercolor="#1f2e43", lightcolor=color, darkcolor=color)
            bar = ttk.Progressbar(wrap, style=style_name, mode="determinate", maximum=100)
            bar.grid(row=0, column=1, sticky="ew", padx=(0, 10))
            self.progress_bars[label] = bar
            tk.Label(wrap, textvariable=value_var, bg=self.controller.theme["panel"], fg="#cbd5e1", font=("Segoe UI", 10, "bold")).grid(row=0, column=2, sticky="e")

    def start_image_download(self) -> None:
        self.controller.dispatch_ui_action("이미지 다운로드 실행", lambda: self.controller.run_action("save-images"), category="assets")

    def start_thumbnail_generation(self) -> None:
        self.controller.dispatch_ui_action("썸네일 생성 실행", self.controller.run_thumbnail_action, category="design")

    def retry_failed_images(self) -> None:
        self.controller.dispatch_ui_action("실패 이미지 재시도", self.controller.refresh_dashboard_data, category="assets")
        self.refresh_view_data(update_preview=True)

    def start_auto_pipeline(self) -> None:
        self.controller.dispatch_ui_action("자동 파이프라인 시작", lambda: self.controller.run_action("run"), category="automation")

    def retry_selected_failed_rows(self) -> None:
        if not self.failed_table or not self.failed_table.selection():
            messagebox.showinfo("선택 필요", "재시도할 실패 행을 먼저 선택해주세요.")
            return
        self.retry_failed_images()

    def refresh_view_data(self, *, update_preview: bool = False) -> None:
        overview = self.controller.dashboard_data.get_image_overview()
        total = int(getattr(self.controller.state.metrics, "total", 0) or 0)
        downloaded = int(overview["metrics"][0][1]) if overview.get("metrics") else 0
        thumbs = int(overview["metrics"][1][1]) if overview.get("metrics") else 0
        failed = int(overview["metrics"][3][1]) if overview.get("metrics") else 0

        self.total_var.set(total)
        self.downloaded_var.set(downloaded)
        self.thumbs_var.set(thumbs)
        self.failed_var.set(failed)
        self.pending_var.set(max(0, total - downloaded))

        ratio = (downloaded / max(1, total)) if total else 0.0
        self.progress_ratio_var.set(ratio)
        self.progress_percent_var.set(f"{int(round(ratio * 100))}%")
        self.progress_done_total_var.set(f"{downloaded:,} / {total:,}")
        self.remaining_var.set(f"{max(0, total - downloaded):,} 건")
        self.stage_image_var.set(f"{downloaded:,} / {total:,}")
        self.stage_thumb_var.set(f"{thumbs:,} / {total:,}")
        self.stage_upload_var.set(f"{max(0, downloaded - thumbs):,} / {total:,}")

        self._draw_progress_ring()
        self._update_status_bars(downloaded=downloaded, thumbs=thumbs, queued=max(0, downloaded - thumbs), total=total)

        if update_preview:
            preview_rows = self._build_preview_rows_from_images_dir(limit=self.PREVIEW_LIMIT)
            self._render_preview_grid(preview_rows)

        self._render_failed_table(overview.get("failed_rows") or [])

    def _draw_progress_ring(self) -> None:
        if not self.progress_ring:
            return
        c = self.progress_ring
        c.delete("all")
        size = min(int(c["width"]), int(c["height"]))
        pad = 10
        extent = -360 * max(0.0, min(1.0, self.progress_ratio_var.get()))
        c.create_oval(pad, pad, size - pad, size - pad, outline="#1f2e43", width=10)
        c.create_arc(pad, pad, size - pad, size - pad, start=90, extent=extent, style=tk.ARC, outline=self.controller.theme["blue"], width=10)
        c.create_text(size / 2, size / 2 - 6, text=self.progress_percent_var.get(), fill=self.controller.theme["blue"], font=("Segoe UI", 22, "bold"))

    def _update_status_bars(self, *, downloaded: int, thumbs: int, queued: int, total: int) -> None:
        total = max(1, total)
        vals = {
            "이미지 저장": int(downloaded / total * 100),
            "썸네일 생성": int(thumbs / total * 100),
            "업로드 대기": int(queued / total * 100),
        }
        for key, bar in self.progress_bars.items():
            bar["value"] = vals.get(key, 0)

    def _render_preview_grid(self, rows: list[Any]) -> None:
        if not self.preview_wrap:
            return

        preview_rows = sorted(rows, key=self._preview_sort_key, reverse=True)[: self.PREVIEW_LIMIT]
        new_keys: list[tuple[str, float]] = []
        for row in preview_rows:
            image_path = self._resolve_first_image_path(str(getattr(row, "image_paths", "") or ""))
            mtime = float(getattr(row, "mtime", 0.0) or 0.0)
            if mtime <= 0 and image_path and os.path.isfile(image_path):
                try:
                    mtime = float(os.path.getmtime(image_path))
                except Exception:
                    mtime = 0.0
            new_keys.append((image_path, mtime))

        has_existing_tiles = bool(self.preview_wrap.winfo_children())
        if has_existing_tiles and new_keys == self._last_preview_keys:
            return

        self._last_preview_keys = new_keys
        for child in self.preview_wrap.winfo_children():
            child.destroy()

        self._preview_photo_refs = []
        self._preview_image_refs.clear()

        if not preview_rows:
            self.build_empty_state(
                self.preview_wrap,
                "최근 저장된 이미지가 없습니다.\n이미지 저장을 실행하면 여기에 표시됩니다.",
            )
            return

        cols = min(self.PREVIEW_COLUMNS, max(1, len(preview_rows)))
        for col in range(cols):
            self.preview_wrap.grid_columnconfigure(col, weight=1, uniform="preview_cols")

        for idx, row in enumerate(preview_rows):
            image_path = self._resolve_first_image_path(str(getattr(row, "image_paths", "") or ""))
            tile = tk.Frame(
                self.preview_wrap,
                bg=SURFACE_BG,
                padx=8,
                pady=8,
                highlightbackground=self.controller.theme["line"],
                highlightthickness=1,
                width=self.PREVIEW_CARD_WIDTH,
                height=self.PREVIEW_IMAGE_BOX_HEIGHT + self.PREVIEW_TEXT_BOX_HEIGHT + 30,
            )
            tile.grid(row=idx // cols, column=idx % cols, sticky="nsew", padx=(0 if idx % cols == 0 else 4, 0), pady=(0, 6))
            tile.grid_propagate(False)

            box = tk.Frame(tile, bg="#0b1525", height=self.PREVIEW_IMAGE_BOX_HEIGHT)
            box.pack(fill=tk.X)
            box.pack_propagate(False)

            imgw = self._build_preview_image_widget(
                box,
                str(getattr(row, "image_paths", "") or ""),
                (str(getattr(row, "brand", "?") or "?")[:2]).upper(),
                key_id=str(getattr(row, "no", idx)),
            )
            imgw.pack(fill=tk.BOTH, expand=True)

            tbox = tk.Frame(tile, bg=SURFACE_BG, height=self.PREVIEW_TEXT_BOX_HEIGHT)
            tbox.pack(fill=tk.X, pady=(6, 0))
            tbox.pack_propagate(False)
            tk.Label(
                tbox,
                text=self._truncate_text(str(getattr(row, "name", "") or ""), limit=30),
                bg=SURFACE_BG,
                fg=self.controller.theme["text"],
                font=("Segoe UI", 9, "bold"),
                wraplength=self.PREVIEW_CARD_WIDTH - 24,
                justify=tk.LEFT,
                anchor="w",
            ).pack(anchor="w")

            self._bind_preview_open(tile, image_path)
            self._bind_preview_open(box, image_path)
            self._bind_preview_open(imgw, image_path)
            self._bind_preview_open(tbox, image_path)

    def _preview_sort_key(self, row: Any) -> float:
        mtime = float(getattr(row, "mtime", 0.0) or 0.0)
        if mtime > 0:
            return mtime
        image_path = self._resolve_first_image_path(str(getattr(row, "image_paths", "") or ""))
        if image_path and os.path.isfile(image_path):
            try:
                return float(os.path.getmtime(image_path))
            except Exception:
                pass
        return 0.0

    def _render_failed_table(self, rows: list[Any]) -> None:
        if not self.failed_table:
            return
        for item in self.failed_table.get_children():
            self.failed_table.delete(item)
        for row in rows[: self.FAILED_LIMIT]:
            self.failed_table.insert(
                "",
                tk.END,
                values=(
                    getattr(row, "no", ""),
                    getattr(row, "name", ""),
                    getattr(row, "brand", ""),
                    getattr(row, "state", "오류"),
                    getattr(row, "updated", "-"),
                ),
            )

    def _resolve_first_image_path(self, image_paths: str) -> str:
        parts = [p.strip() for p in (image_paths or "").split(",") if p.strip()]
        if not parts:
            return ""

        try:
            images_root = os.path.abspath(os.path.expanduser(self.controller._get_configured_images_dir()))
        except Exception:
            images_root = ""

        for raw in parts:
            expanded = os.path.expanduser(raw)
            candidates = [os.path.abspath(expanded)]
            if not os.path.isabs(expanded) and images_root:
                candidates.append(os.path.abspath(os.path.join(images_root, expanded)))
            for cand in candidates:
                if os.path.isfile(cand):
                    return cand
                if os.path.isdir(cand):
                    latest = self._latest_image_in_dir(cand)
                    if latest:
                        return latest
        return ""

    def _latest_image_in_dir(self, root_dir: str) -> str:
        exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
        latest_path = ""
        latest_mtime = -1.0
        for dirpath, _dirnames, filenames in os.walk(root_dir):
            for name in filenames:
                if os.path.splitext(name)[1].lower() not in exts:
                    continue
                path = os.path.join(dirpath, name)
                try:
                    mtime = float(os.path.getmtime(path))
                except Exception:
                    continue
                if mtime > latest_mtime:
                    latest_mtime = mtime
                    latest_path = path
        return latest_path

    def _build_preview_image_widget(self, parent: tk.Widget, image_paths: str, fallback_text: str, *, key_id: str) -> tk.Widget:
        box_w = self.PREVIEW_CARD_WIDTH - 16
        box_h = self.PREVIEW_IMAGE_BOX_HEIGHT
        path = self._resolve_first_image_path(image_paths)

        if path and Image is not None and ImageTk is not None:
            try:
                mtime = os.path.getmtime(path)
                cache_key = (path, mtime, box_w, box_h)
                photo = self._image_cache.get(cache_key)
                if photo is None:
                    im = Image.open(path)
                    im.thumbnail((box_w, box_h))
                    bg = Image.new("RGB", (box_w, box_h), (11, 21, 37))
                    paste_x = (box_w - im.width) // 2
                    paste_y = (box_h - im.height) // 2
                    bg.paste(im, (paste_x, paste_y))
                    photo = ImageTk.PhotoImage(bg)
                    self._image_cache[cache_key] = photo
                self._preview_photo_refs.append(photo)
                self._preview_image_refs[key_id] = photo
                return tk.Label(parent, image=photo, bg="#0b1525")
            except Exception:
                pass

        canvas = tk.Canvas(parent, width=box_w, height=box_h, bg="#0b1525", highlightthickness=0)
        canvas.create_rectangle(14, 14, box_w - 14, box_h - 14, fill="#16263d", outline="#28456b")
        canvas.create_text(box_w / 2, box_h / 2, text=fallback_text or "?", fill="#93c5fd", font=("Segoe UI", 18, "bold"))
        return canvas

    def _build_preview_rows_from_images_dir(self, *, limit: int) -> list[_PreviewRow]:
        try:
            root = self.controller._get_configured_images_dir()
        except Exception:
            return []

        latest_items = get_latest_preview_images(root, limit=limit)
        out: list[_PreviewRow] = []
        for idx, item in enumerate(latest_items[:limit], start=1):
            path = str(item.get("path", "") or "")
            folder = str(item.get("folder", "") or os.path.basename(os.path.dirname(path)))
            name = str(item.get("name", "") or folder or os.path.basename(path))
            out.append(
                _PreviewRow(
                    no=str(idx),
                    name=name,
                    brand=(folder[:2].upper() if folder else "IMG"),
                    state="완료",
                    image_paths=path,
                    mtime=float(item.get("mtime", 0.0) or 0.0),
                )
            )
        return out

    def _bind_preview_open(self, widget: tk.Widget, image_path: str) -> None:
        if not image_path:
            return
        widget.configure(cursor="hand2")
        widget.bind("<Double-Button-1>", lambda _e, p=image_path: self._open_preview_image(p))

    def _open_preview_image(self, image_path: str) -> None:
        if not image_path or not os.path.isfile(image_path):
            messagebox.showwarning("이미지 열기 실패", "이미지 파일을 찾을 수 없습니다.")
            return
        try:
            if hasattr(os, "startfile"):
                os.startfile(image_path)
            else:
                webbrowser.open(f"file://{image_path}")
        except Exception as exc:
            messagebox.showerror("이미지 열기 실패", f"이미지 열기 중 오류가 발생했습니다.\n{exc}")

    def _schedule_refresh(self) -> None:
        if self._refresh_job:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
        self._refresh_job = self.after(self.REFRESH_MS, self._refresh_tick)

    def _refresh_tick(self) -> None:
        self._refresh_job = None
        try:
            self.refresh_view_data(update_preview=False)
        finally:
            if self.winfo_exists():
                self._schedule_refresh()

    def destroy(self) -> None:
        if self._refresh_job:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
            self._refresh_job = None
        super().destroy()

    def _formatted_int_var(self, src_var: tk.IntVar) -> tk.StringVar:
        out = tk.StringVar(value=f"{src_var.get():,}")
        src_var.trace_add("write", lambda *_: out.set(f"{src_var.get():,}"))
        return out

    @staticmethod
    def _truncate_text(text: str, *, limit: int) -> str:
        value = (text or "").strip()
        return value if len(value) <= limit else value[: max(0, limit - 1)].rstrip() + "…"


def build_image_thumbnail_page(parent: tk.Widget, controller) -> ImageThumbnailPage:
    return ImageThumbnailPage(parent, controller)
