"""Image/thumbnail helper functions."""

import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from typing import Dict, List

from bs4 import BeautifulSoup

from config.app_config import BRAND_COLUMN, BRAND_EN_COLUMN
from config.config_service import DEFAULT_PROFILE_NAME, load_config
from services.crawler_service import normalize_image_source as svc_normalize_image_source

DEFAULT_THUMBNAIL_FOOTER_SUFFIX = "angduss k-closet"


def sanitize_path_component(value: str) -> str:
    """Sanitize filename/foldername component."""
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", (value or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" ._") or "item"


def resolve_image_folder_from_paths(image_paths: str) -> str:
    """Return folder path from comma-separated image paths."""
    parts = [part.strip() for part in (image_paths or "").split(",") if part.strip()]
    if not parts:
        return ""
    first_path = os.path.abspath(os.path.expanduser(parts[0].replace("/", os.sep)))
    return os.path.dirname(first_path)


def build_thumbnail_brand(existing_values: Dict[str, str]) -> str:
    """Return thumbnail brand text with priority: EN brand > KR brand."""
    brand = (existing_values.get(BRAND_EN_COLUMN, "") or "").strip()
    if brand:
        return brand
    brand = (existing_values.get(BRAND_COLUMN, "") or "").strip()
    return brand or "BRAND"


def get_thumbnail_footer_suffix() -> str:
    """Return thumbnail footer suffix from env/config, or fallback default."""
    env_value = (os.environ.get("AUTO_SHOP_THUMBNAIL_FOOTER_SUFFIX") or "").strip()
    if env_value:
        return env_value

    env_data_dir = (os.environ.get("AUTO_SHOP_DATA_DIR") or "").strip()
    if env_data_dir:
        data_dir = os.path.abspath(os.path.expanduser(env_data_dir))
    else:
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            data_dir = os.path.join(local_app_data, "auto_shop")
        else:
            data_dir = os.path.join(os.path.expanduser("~"), ".auto_shop")
    cfg_path = os.path.join(data_dir, "sheets_config.json")
    try:
        if os.path.exists(cfg_path):
            import json

            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if isinstance(cfg, dict):
                configured = (cfg.get("thumbnail_footer_suffix") or "").strip()
                if configured:
                    return configured
    except Exception:
        pass
    return DEFAULT_THUMBNAIL_FOOTER_SUFFIX


def compose_thumbnail_footer(brand: str) -> str:
    suffix = get_thumbnail_footer_suffix()
    return f"{brand} / {suffix}"


def get_thumbnail_blur_faces_enabled() -> bool:
    """Return whether generated thumbnails should blur detected faces."""
    env_value = (os.environ.get("AUTO_SHOP_THUMBNAIL_BLUR_FACES") or "").strip().lower()
    if env_value in {"1", "true", "yes", "on"}:
        return True
    if env_value in {"0", "false", "no", "off"}:
        return False

    profile_name = (os.environ.get("AUTO_SHOP_PROFILE") or DEFAULT_PROFILE_NAME).strip() or DEFAULT_PROFILE_NAME
    try:
        config = load_config(profile_name, create_if_missing=False)
        options = ((config.get("crawling") or {}).get("options") or {})
        if "blur_faces" in options:
            return bool(options.get("blur_faces"))
    except Exception:
        pass

    return True


def create_thumbnail_for_folder(folder_path: str, brand: str) -> bool:
    """Create thumbnail for a folder by running make_thumbnails.py."""
    folder = os.path.abspath(os.path.expanduser(folder_path))
    if not os.path.isdir(folder):
        print(f"    썸네일 스킵: 폴더가 없습니다 -> {folder}")
        return False

    style = "split"
    footer = compose_thumbnail_footer(brand)
    project_root = os.path.dirname(os.path.dirname(__file__))
    thumbnail_script_path = os.path.join(project_root, "make_thumbnails.py")
    command = [
        sys.executable,
        thumbnail_script_path,
        folder,
        "--style",
        style,
        "--brand",
        brand,
        "--footer",
        footer,
    ]
    if get_thumbnail_blur_faces_enabled():
        command.append("--blur-face")
    try:
        completed = subprocess.run(
            command,
            cwd=project_root,
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


def download_thumbnail_images(
    image_urls: List[str],
    folder_name: str,
    images_root: str,
    max_thumbnail_images: int,
) -> str:
    """Download product images and return comma-separated local file paths."""
    if not image_urls:
        return ""

    from datetime import date as _date

    date_folder = _date.today().strftime("%Y%m%d")
    image_dir = os.path.join(images_root, date_folder, sanitize_path_component(folder_name))
    os.makedirs(image_dir, exist_ok=True)

    saved_paths: List[str] = []
    for index, image_url in enumerate(image_urls[:max_thumbnail_images], start=1):
        try:
            parsed = urllib.parse.urlparse(image_url)
            ext = os.path.splitext(parsed.path)[1].lower()
            if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
                ext = ".jpg"

            file_name = f"{index:02d}{ext}"
            file_path = os.path.join(image_dir, file_name)
            request = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=30) as response:
                with open(file_path, "wb") as image_file:
                    image_file.write(response.read())

            saved_paths.append(file_path.replace("\\", "/"))
        except Exception as image_error:
            print(f"    이미지 다운로드 스킵: {image_error}")

    return ",".join(saved_paths)


def extract_brand_logo_url(soup: BeautifulSoup, product_json: Dict[str, object]) -> str:
    """Extract probable brand logo URL from page/json."""
    candidates: List[str] = []

    def add_candidate(src: str):
        normalized = svc_normalize_image_source(src or "")
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    if isinstance(product_json, dict):
        brand_obj = product_json.get("brand")
        if isinstance(brand_obj, dict):
            for key in (
                "logoImageUrl",
                "logoImage",
                "logoUrl",
                "logo",
                "imageUrl",
                "image",
                "thumbnail",
            ):
                value = brand_obj.get(key)
                if isinstance(value, str):
                    add_candidate(value)

    for img in soup.select('a[href*="/brand/"] img'):
        for attr in ("src", "data-src", "data-original", "data-lazy-src"):
            src = img.get(attr, "")
            if src:
                add_candidate(src)

    for img in soup.select('img[alt*="logo" i], img[class*="logo" i], img[src*="logo" i]'):
        for attr in ("src", "data-src", "data-original", "data-lazy-src"):
            src = img.get(attr, "")
            if src:
                add_candidate(src)

    if not candidates:
        return ""

    for url in candidates:
        lower = url.lower()
        if "brand" in lower or "logo" in lower:
            return url
    return candidates[0]


def download_brand_logo(logo_url: str, folder_name: str, images_root: str, image_paths: str = "") -> str:
    """Save brand logo as __brand_logo.png in product image folder."""
    if not logo_url:
        return ""

    image_dir = resolve_image_folder_from_paths(image_paths)
    if not image_dir:
        from datetime import date as _date

        date_folder = _date.today().strftime("%Y%m%d")
        image_dir = os.path.join(images_root, date_folder, sanitize_path_component(folder_name))
    os.makedirs(image_dir, exist_ok=True)

    try:
        logo_path = os.path.join(image_dir, "__brand_logo.png")
        request = urllib.request.Request(logo_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            raw_bytes = response.read()
        try:
            from io import BytesIO
            from PIL import Image

            with Image.open(BytesIO(raw_bytes)) as img:
                img.convert("RGBA").save(logo_path, format="PNG")
        except Exception:
            with open(logo_path, "wb") as f:
                f.write(raw_bytes)
        print(f"    브랜드 로고 저장: {logo_path}")
        return logo_path.replace("\\", "/")
    except Exception as e:
        print(f"    브랜드 로고 저장 실패: {e}")
        return ""
