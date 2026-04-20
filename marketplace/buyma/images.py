"""BUYMA image path resolution helpers."""

import glob
import os
from pathlib import Path
from typing import List

from marketplace.common.runtime import get_runtime_data_dir


def resolve_image_files(image_paths_cell: str) -> List[str]:
    """Resolve image file list from sheet cell path string."""
    if not image_paths_cell:
        return []

    images_root = os.path.join(get_runtime_data_dir(), "images")
    workspace_images_root = str(Path(__file__).resolve().parents[2] / "images")

    files = []
    candidate_dirs = []
    for part in image_paths_cell.split(","):
        path = part.strip()
        if not path:
            continue

        norm_path = path.replace("\\", "/").lstrip("./")
        if norm_path.lower().startswith("images/"):
            norm_path = norm_path[len("images/"):]

        if os.path.isabs(path):
            candidate_paths = [path]
        else:
            candidate_paths = [
                os.path.join(images_root, norm_path),
                os.path.join(workspace_images_root, norm_path),
            ]

        for full_path in candidate_paths:
            if os.path.isfile(full_path):
                files.append(os.path.abspath(full_path))
                candidate_dirs.append(os.path.dirname(os.path.abspath(full_path)))
                break
            if os.path.isdir(full_path):
                for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
                    files.extend(sorted(glob.glob(os.path.join(full_path, ext))))
                candidate_dirs.append(os.path.abspath(full_path))
                break

    priority_names = [
        "00_thumb_main.jpg",
        "00_thumbnail.jpg",
        "00_main.jpg",
    ]
    prepend = []
    seen_dirs = set()
    for directory in candidate_dirs:
        if not directory or directory in seen_dirs:
            continue
        seen_dirs.add(directory)
        for name in priority_names:
            candidate = os.path.join(directory, name)
            if os.path.isfile(candidate):
                prepend.append(os.path.abspath(candidate))
                break

    if prepend:
        existing = set(prepend)
        files = prepend + [file_path for file_path in files if file_path not in existing]

    return files
