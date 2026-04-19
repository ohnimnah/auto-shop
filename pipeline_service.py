"""Pipeline/status decision helpers."""


def determine_progress_status(
    margin_rate: float | None,
    margin_threshold_percent: float,
    status_hold: str,
    status_crawled: str,
) -> str:
    """Compute next progress status from margin rate."""
    if margin_rate is not None and margin_rate < margin_threshold_percent:
        return status_hold
    return status_crawled


def is_crawler_ready_status(status: str, status_waiting: str, status_new: str) -> bool:
    """Return whether crawler worker can pick this row."""
    normalized = (status or "").strip()
    return normalized in {"", status_waiting, status_new, "NEW"}


def is_image_ready_status(status: str, status_crawled: str, status_image_ready: str) -> bool:
    """Return whether image worker can pick this row."""
    normalized = (status or "").strip()
    return normalized in {status_crawled, "CRAWLED", status_image_ready}


def is_thumbnail_ready_status(
    status: str,
    status_images_saved: str,
    status_thumbnail_ready: str,
) -> bool:
    """Return whether thumbnail worker can pick this row."""
    normalized = (status or "").strip()
    return normalized in {status_images_saved, "IMAGES_SAVED", status_thumbnail_ready}
