"""Sidebar navigation and shortcut definitions."""

NAV_ITEMS = [
    ("대시보드", True),
    ("수집 / 정찰", False),
    ("이미지 / 썸네일", False),
    ("BUYMA 업로드", False),
    ("감시 / 자동화", False),
    ("관리 / 설정", False),
]

SHORTCUTS = [
    ("전체 자동화 시작", "watch", "green"),
    ("감시 모드 시작", "watch", "blue"),
    ("실패 건 재처리", "upload-review", "orange"),
    ("현재 작업 중지", "stop", "red"),
    ("로그 폴더 열기", "logs", "neutral"),
    ("이미지 폴더 설정", "images-dir", "neutral"),
]

