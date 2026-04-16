import argparse
import os
import sys
from pathlib import Path
import re
from typing import Optional

# Windows cp949 터미널에서 유니코드 출력 오류 방지
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") in ("cp949", "euckr"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
LOGO_EXTS = (".png", ".webp", ".jpg", ".jpeg")
LOGO_BASENAMES = {"__brand_logo", "_brand_logo", "brand_logo", "logo"}


def iter_images(input_path: Path):
    if input_path.is_file() and input_path.suffix.lower() in IMAGE_EXTS:
        if input_path.stem.lower() in LOGO_BASENAMES:
            return
        yield input_path
        return

    if input_path.is_dir():
        for p in sorted(input_path.iterdir()):
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
                if p.stem.lower() in LOGO_BASENAMES:
                    continue
                yield p


def _load_font(size: int, bold: bool = False):
    candidates = []
    if os.name == "nt":
        win_fonts = Path("C:/Windows/Fonts")
        if bold:
            candidates += [win_fonts / "malgunbd.ttf", win_fonts / "arialbd.ttf"]
        else:
            candidates += [win_fonts / "malgun.ttf", win_fonts / "arial.ttf"]

    for p in candidates:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def _open_rgb(path: Path) -> Image.Image:
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    if im.mode == "L":
        im = im.convert("RGB")
    return im


def _normalize_brand_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _find_brand_logo(
    brand: str,
    input_path: Path,
    explicit_logo: str = "",
    explicit_logo_dir: str = "",
) -> Optional[Path]:
    # Product-folder fixed logo filename (set by crawler) has highest priority.
    fixed_names = ["__brand_logo", "_brand_logo", "brand_logo", "logo"]
    if input_path.is_dir():
        for base in fixed_names:
            for ext in LOGO_EXTS:
                p = input_path / f"{base}{ext}"
                if p.exists() and p.is_file():
                    return p

    if explicit_logo:
        p = Path(explicit_logo).expanduser()
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        if p.exists() and p.is_file():
            return p
        return None

    script_dir = Path(__file__).resolve().parent
    search_dirs = []
    if explicit_logo_dir:
        d = Path(explicit_logo_dir).expanduser()
        if not d.is_absolute():
            d = (Path.cwd() / d).resolve()
        search_dirs.append(d)

    search_dirs += [
        script_dir / "logos",
        script_dir / "brand_logos",
        script_dir / "images" / "logos",
        script_dir / "images" / "brand_logos",
    ]

    if input_path.is_dir():
        search_dirs += [input_path, input_path.parent]
    else:
        search_dirs += [input_path.parent]

    brand_raw = (brand or "").strip()
    if not brand_raw:
        return None

    base_names = [brand_raw, brand_raw.replace(" ", "_"), brand_raw.replace(" ", "-")]
    normalized_target = _normalize_brand_key(brand_raw)

    for d in search_dirs:
        if not d.exists() or not d.is_dir():
            continue
        for base in base_names:
            for ext in LOGO_EXTS:
                candidate = d / f"{base}{ext}"
                if candidate.exists() and candidate.is_file():
                    return candidate
        for p in d.iterdir():
            if not p.is_file() or p.suffix.lower() not in LOGO_EXTS:
                continue
            if _normalize_brand_key(p.stem) == normalized_target:
                return p
    return None


def _paste_brand_logo(canvas: Image.Image, logo_path: Path, left_box, size: int) -> bool:
    try:
        lx, ly, lw, lh = left_box
        with Image.open(logo_path).convert("RGBA") as logo:
            max_w = max(90, int(lw * 0.27))
            max_h = max(36, int(lh * 0.09))
            fitted = ImageOps.contain(logo, (max_w, max_h), method=Image.Resampling.LANCZOS)

        pad_x = max(10, size // 60)
        pad_y = max(6, size // 90)
        badge_w = fitted.width + pad_x * 2
        badge_h = fitted.height + pad_y * 2
        # Top-left placement with safe margins.
        outer_margin_x = max(16, size // 28)
        outer_margin_y = max(14, size // 34)
        bx = lx + outer_margin_x
        by = ly + outer_margin_y

        canvas_rgba = canvas.convert("RGBA")
        px = bx + (badge_w - fitted.width) // 2
        py = by + (badge_h - fitted.height) // 2
        # Add a subtle white outline so logos remain visible on dark/complex backgrounds.
        alpha = fitted.getchannel("A")
        outline = alpha.filter(ImageFilter.MaxFilter(3))
        white_outline = Image.new("RGBA", fitted.size, (255, 255, 255, 0))
        white_outline.putalpha(outline)
        canvas_rgba.alpha_composite(white_outline, (px, py))
        canvas_rgba.alpha_composite(fitted, (px, py))
        canvas.paste(canvas_rgba.convert("RGB"))
        return True
    except Exception:
        return False


def _blur_faces(pil_img: Image.Image, blur_radius: int = 14) -> Image.Image:
    """Detect faces and apply Gaussian blur only on face areas."""
    if cv2 is None or np is None:
        return pil_img

    arr = np.array(pil_img)
    if arr.size == 0:
        return pil_img

    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)

    # 이미지 상단 55% 영역에서만 탐지 (하반신 오탐 방지)
    h_limit = int(gray.shape[0] * 0.55)
    gray_top = gray[:h_limit, :]

    faces = face_cascade.detectMultiScale(
        gray_top,
        scaleFactor=1.05,
        minNeighbors=7,
        minSize=(60, 60),
        maxSize=(int(gray.shape[1] * 0.5), int(gray.shape[0] * 0.5)),
    )

    if len(faces) == 0:
        return pil_img

    out = pil_img.copy()
    for (x, y, w, h) in faces:
        # Face box padding for natural blur coverage.
        px = int(w * 0.2)
        py = int(h * 0.25)
        x1 = max(0, x - px)
        y1 = max(0, y - py)
        x2 = min(out.width, x + w + px)
        y2 = min(out.height, y + h + py)
        if x2 <= x1 or y2 <= y1:
            continue
        face_region = out.crop((x1, y1, x2, y2))
        blurred_region = face_region.filter(ImageFilter.GaussianBlur(radius=blur_radius))

        # Apply blur with an elliptical mask to follow face shape instead of a rectangle.
        mask = Image.new("L", (x2 - x1, y2 - y1), 0)
        draw = ImageDraw.Draw(mask)
        inset_x = max(1, int((x2 - x1) * 0.06))
        inset_y = max(1, int((y2 - y1) * 0.04))
        draw.ellipse(
            (inset_x, inset_y, (x2 - x1) - inset_x, (y2 - y1) - inset_y),
            fill=255,
        )
        mask = mask.filter(ImageFilter.GaussianBlur(radius=max(2, blur_radius // 2)))
        out.paste(blurred_region, (x1, y1), mask)
    return out


def _paste_cover(canvas: Image.Image, src: Path, box, blur_faces: bool = False, blur_radius: int = 14):
    """Legacy name kept for compatibility.
    Preserve the full source image (no crop) and fill remaining area with a soft background.
    """
    x, y, w, h = box
    with _open_rgb(src) as im:
        fitted = ImageOps.contain(im, (w, h), method=Image.Resampling.LANCZOS)
        # Use a resized blurred backdrop to avoid harsh empty bands while keeping full image visible.
        bg = im.resize((w, h), Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(radius=18))
    if blur_faces:
        fitted = _blur_faces(fitted, blur_radius=blur_radius)
    px = (w - fitted.width) // 2
    py = (h - fitted.height) // 2
    bg.paste(fitted, (px, py))
    canvas.paste(bg, (x, y))


def _paste_contain(canvas: Image.Image, src: Path, box, bg=(255, 255, 255), blur_faces: bool = False, blur_radius: int = 14):
    x, y, w, h = box
    with _open_rgb(src) as im:
        fitted = ImageOps.contain(im, (w, h), method=Image.Resampling.LANCZOS)
    if blur_faces:
        fitted = _blur_faces(fitted, blur_radius=blur_radius)
    panel = Image.new("RGB", (w, h), bg)
    px = (w - fitted.width) // 2
    py = (h - fitted.height) // 2
    panel.paste(fitted, (px, py))
    canvas.paste(panel, (x, y))


def compose_split_style(
    images,
    dst: Path,
    size: int,
    title: str,
    footer: str,
    bg=(255, 255, 255),
    blur_faces: bool = False,
    blur_radius: int = 14,
    brand_logo: Optional[Path] = None,
):
    """예시의 의류형 썸네일 스타일: 좌측 메인컷 + 우측 2컷 + 하단 블랙 바."""
    if len(images) < 1:
        raise ValueError("split 스타일은 최소 1장이 필요합니다")
    # 이미지가 3장 미만이면 반복해서 채운다
    while len(images) < 3:
        images = images + images
    images = images[:3]

    canvas = Image.new("RGB", (size, size), bg)
    margin = max(20, size // 36)
    footer_h = max(52, size // 14)
    top_h = size - (margin * 2) - footer_h
    inner_w = size - margin * 2
    gap = max(4, size // 200)

    left_w = int(inner_w * 0.56)
    right_w = inner_w - left_w - gap
    right_h = (top_h - gap) // 2

    left_box = (margin, margin, left_w, top_h)
    right_top_box = (margin + left_w + gap, margin, right_w, right_h)
    right_bottom_box = (margin + left_w + gap, margin + right_h + gap, right_w, top_h - right_h - gap)

    _paste_cover(canvas, images[0], left_box, blur_faces=blur_faces, blur_radius=blur_radius)
    _paste_contain(canvas, images[1], right_top_box, bg=bg, blur_faces=blur_faces, blur_radius=blur_radius)
    _paste_contain(canvas, images[2], right_bottom_box, bg=bg, blur_faces=blur_faces, blur_radius=blur_radius)

    draw = ImageDraw.Draw(canvas)

    logo_applied = False
    if brand_logo:
        logo_applied = _paste_brand_logo(canvas, brand_logo, left_box, size)

    if title and not logo_applied:
        # 첫 번째 큰 사진 박스 내부 상단 중앙(좌우대칭) 정렬
        title_size = max(44, size // 9)
        title_font = _load_font(title_size, bold=True)
        max_text_w = max(80, left_w - (size // 20))
        while True:
            bbox = draw.textbbox((0, 0), title, font=title_font)
            tw = bbox[2] - bbox[0]
            if tw <= max_text_w or title_size <= 28:
                break
            title_size -= 2
            title_font = _load_font(title_size, bold=True)

        bbox = draw.textbbox((0, 0), title, font=title_font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = left_box[0] + (left_box[2] - tw) // 2
        ty = left_box[1] + max(10, size // 40)
        # 상단에서 너무 내려가지 않게 최소한의 여백만 유지
        ty = min(ty, left_box[1] + max(10, (left_box[3] - th) // 6))
        draw.text(
            (tx, ty),
            title,
            fill=(255, 255, 255),
            font=title_font,
            stroke_width=max(2, title_size // 18),
            stroke_fill=(0, 0, 0),
        )

    draw.rectangle((0, size - footer_h, size, size), fill=(255, 255, 255))
    footer_font = _load_font(max(22, size // 24), bold=True)
    tw, th = draw.textbbox((0, 0), footer, font=footer_font)[2:]
    tx = (size - tw) // 2
    ty = size - footer_h + (footer_h - th) // 2
    draw.text((tx, ty), footer, fill=(0, 0, 0), font=footer_font)

    dst.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dst, quality=95, optimize=True)


def compose_banner_style(
    images,
    dst: Path,
    size: int,
    footer: str,
    bg=(255, 255, 255),
    blur_faces: bool = False,
    blur_radius: int = 14,
):
    """예시의 안경형 스타일: 상단 와이드 + 중간 텍스트 밴드 + 하단 3컷."""
    if len(images) < 1:
        raise ValueError("banner 스타일은 최소 1장이 필요합니다")
    # 이미지가 4장 미만이면 반복해서 채운다
    while len(images) < 4:
        images = images + images
    images = images[:4]

    canvas = Image.new("RGB", (size, size), bg)
    margin = max(20, size // 30)
    top_h = int(size * 0.34)
    band_h = int(size * 0.14)
    gap = max(8, size // 100)

    top_box = (margin, margin, size - margin * 2, top_h)   # 양옆 여백
    band_y = margin + top_h
    bottom_y = band_y + band_h + gap
    bottom_h = size - bottom_y - margin
    cell_w = (size - margin * 2 - gap * 2) // 3

    _paste_cover(canvas, images[0], top_box, blur_faces=blur_faces, blur_radius=blur_radius)

    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, band_y, size, band_y + band_h), fill=(245, 245, 245))

    # 밴드 텍스트: 너비에 맞게 폰트 자동 축소
    max_text_w = size - margin * 4
    fsize = max(22, size // 22)
    footer_font = _load_font(fsize, bold=True)
    tw, th = draw.textbbox((0, 0), footer, font=footer_font)[2:]
    while tw > max_text_w and fsize > 14:
        fsize -= 1
        footer_font = _load_font(fsize, bold=True)
        tw, th = draw.textbbox((0, 0), footer, font=footer_font)[2:]
    draw.text(((size - tw) // 2, band_y + (band_h - th) // 2), footer, fill=(0, 0, 0), font=footer_font)

    _paste_contain(canvas, images[1], (margin, bottom_y, cell_w, bottom_h), bg=bg, blur_faces=blur_faces, blur_radius=blur_radius)
    _paste_contain(canvas, images[2], (margin + cell_w + gap, bottom_y, cell_w, bottom_h), bg=bg, blur_faces=blur_faces, blur_radius=blur_radius)
    _paste_contain(canvas, images[3], (margin + (cell_w + gap) * 2, bottom_y, cell_w, bottom_h), bg=bg, blur_faces=blur_faces, blur_radius=blur_radius)

    dst.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dst, quality=95, optimize=True)


def compose_simple_logo_style(
    images,
    dst: Path,
    size: int,
    bg=(255, 255, 255),
    blur_faces: bool = False,
    blur_radius: int = 14,
    brand_logo: Optional[Path] = None,
):
    """1장/2장 전용 단순 레이아웃:
    - 1장: 원본 1장만 표시 + 로고 좌상단
    - 2장: 좌우 50:50 표시 + 로고 좌상단
    """
    if len(images) not in (1, 2):
        raise ValueError("simple 스타일은 1장 또는 2장만 지원합니다")

    canvas = Image.new("RGB", (size, size), bg)
    margin = max(12, size // 60)

    if len(images) == 1:
        box = (margin, margin, size - margin * 2, size - margin * 2)
        _paste_contain(canvas, images[0], box, bg=bg, blur_faces=blur_faces, blur_radius=blur_radius)
    else:
        gap = max(4, size // 200)
        inner_w = size - margin * 2
        half_w = (inner_w - gap) // 2
        left_box = (margin, margin, half_w, size - margin * 2)
        right_box = (margin + half_w + gap, margin, inner_w - half_w - gap, size - margin * 2)
        _paste_contain(canvas, images[0], left_box, bg=bg, blur_faces=blur_faces, blur_radius=blur_radius)
        _paste_contain(canvas, images[1], right_box, bg=bg, blur_faces=blur_faces, blur_radius=blur_radius)

    if brand_logo:
        _paste_brand_logo(canvas, brand_logo, (0, 0, size, size), size)

    dst.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dst, quality=95, optimize=True)


def main():
    parser = argparse.ArgumentParser(description="Create one style collage thumbnail")
    parser.add_argument("input", help="Input image file or folder")
    parser.add_argument("--size", type=int, default=1000, help="Square size (default: 1000)")
    parser.add_argument("--output", default="", help="Output file path (default: <input>_thumb_<size>.jpg)")
    parser.add_argument("--style", choices=["split", "banner"], default="split", help="Layout style")
    parser.add_argument("--title", default="", help="Top-left title text (split style)")
    parser.add_argument("--brand", default="", help="Brand name text (if set, used as title)")
    parser.add_argument("--brand-logo", default="", help="Brand logo image path (optional)")
    parser.add_argument("--logo-dir", default="", help="Directory to search brand logo file (optional)")
    parser.add_argument("--footer", default="", help="Bottom/footer text")
    parser.add_argument("--first-name", default="00_thumb_main.jpg", help="Filename when saving into source folder")
    parser.add_argument("--blur-face", action="store_true", help="Apply Gaussian blur on detected faces")
    parser.add_argument("--blur-radius", type=int, default=14, help="Face blur radius")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    if args.output:
        output_file = Path(args.output).expanduser().resolve()
    else:
        if input_path.is_dir():
            # 기본은 원본 폴더에 첫 파일로 오도록 저장
            output_file = input_path / args.first_name
        else:
            output_file = input_path.parent / args.first_name

    images = list(iter_images(input_path))
    if not images:
        print("No image files found.")
        return

    title_text = (args.brand.strip() or args.title.strip())
    footer_text = args.footer.strip() or f"{(args.brand.strip() or input_path.name)} / angduss k-closet"
    logo_path = _find_brand_logo(
        brand=args.brand.strip() or title_text,
        input_path=input_path,
        explicit_logo=args.brand_logo,
        explicit_logo_dir=args.logo_dir,
    )
    if logo_path:
        print(f"Brand logo found: {logo_path}")
    bg = (255, 255, 255)

    if len(images) <= 2:
        compose_simple_logo_style(
            images,
            output_file,
            args.size,
            bg=bg,
            blur_faces=args.blur_face,
            blur_radius=args.blur_radius,
            brand_logo=logo_path,
        )
        style_used = "simple"
    elif args.style == "split":
        compose_split_style(
            images,
            output_file,
            args.size,
            title_text,
            footer_text,
            bg=bg,
            blur_faces=args.blur_face,
            blur_radius=args.blur_radius,
            brand_logo=logo_path,
        )
        style_used = "split"
    else:
        compose_banner_style(
            images,
            output_file,
            args.size,
            footer_text,
            bg=bg,
            blur_faces=args.blur_face,
            blur_radius=args.blur_radius,
        )
        style_used = "banner"

    print(f"Created 1 {style_used} thumbnail from {len(images)} images: {output_file}")


if __name__ == "__main__":
    main()
