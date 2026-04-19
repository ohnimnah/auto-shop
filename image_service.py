"""Image/thumbnail helper functions."""

import os
import subprocess
import sys
from typing import Dict

from app_config import BRAND_COLUMN, BRAND_EN_COLUMN


def resolve_image_folder_from_paths(image_paths: str) -> str:
    """콤마 구분 image_paths에서 첫 이미지의 폴더 경로를 반환한다."""
    parts = [part.strip() for part in (image_paths or "").split(",") if part.strip()]
    if not parts:
        return ""
    first_path = os.path.abspath(os.path.expanduser(parts[0].replace("/", os.sep)))
    return os.path.dirname(first_path)


def build_thumbnail_brand(existing_values: Dict[str, str]) -> str:
    """썸네일용 브랜드명을 우선순위대로 반환한다."""
    brand = (existing_values.get(BRAND_EN_COLUMN, "") or "").strip()
    if brand:
        return brand
    brand = (existing_values.get(BRAND_COLUMN, "") or "").strip()
    return brand or "BRAND"


def create_thumbnail_for_folder(folder_path: str, brand: str) -> bool:
    """이미지 폴더에서 썸네일을 생성한다."""
    folder = os.path.abspath(os.path.expanduser(folder_path))
    if not os.path.isdir(folder):
        print(f"    썸네일 스킵: 폴더가 없습니다 -> {folder}")
        return False

    style = "split"
    footer = f"{brand} / angduss k-closet"
    command = [
        sys.executable,
        os.path.join(os.path.dirname(__file__), "make_thumbnails.py"),
        folder,
        "--style",
        style,
        "--brand",
        brand,
        "--footer",
        footer,
        "--blur-face",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=os.path.dirname(__file__),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if completed.stdout.strip():
            print(completed.stdout.strip())
        if completed.stderr.strip():
            print(completed.stderr.strip())
        thumb_path = os.path.join(folder, "00_thumb_main.jpg")
        if completed.returncode == 0 and os.path.exists(thumb_path):
            print(f"    썸네일 생성 완료: {thumb_path} ({style})")
            return True
        print(f"    썸네일 생성 실패 (코드 {completed.returncode})")
        return False
    except Exception as e:
        print(f"    썸네일 생성 오류: {e}")
        return False
