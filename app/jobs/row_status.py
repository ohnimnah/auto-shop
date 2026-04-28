from __future__ import annotations

from enum import Enum


class RowStatus(str, Enum):
    NEW = "신규"
    CRAWLED = "정찰완료"
    IMAGE_DONE = "이미지완료"
    UPLOADED = "업로드완료"
    FAILED = "실패"

