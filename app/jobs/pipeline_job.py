from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from app.jobs.row_status import RowStatus


@dataclass
class PipelineRowResult:
    row_id: int
    status: RowStatus
    error: str = ""


@dataclass
class PipelineJobResult:
    rows: list[PipelineRowResult] = field(default_factory=list)


class PipelineJob:
    """Run crawl -> image -> upload per row without stopping the full batch."""

    def __init__(
        self,
        *,
        crawl_one: Callable[[dict], bool],
        image_one: Callable[[dict], bool],
        upload_one: Callable[[dict], bool],
        update_status: Callable[[int, RowStatus, str], None],
    ) -> None:
        self.crawl_one = crawl_one
        self.image_one = image_one
        self.upload_one = upload_one
        self.update_status = update_status

    def run(self, rows: Iterable[dict]) -> PipelineJobResult:
        result = PipelineJobResult()
        for row in rows:
            row_id = int(row.get("row_num", 0) or 0)
            try:
                if not self.crawl_one(row):
                    self.update_status(row_id, RowStatus.FAILED, "crawl_failed")
                    result.rows.append(PipelineRowResult(row_id=row_id, status=RowStatus.FAILED, error="crawl_failed"))
                    continue
                self.update_status(row_id, RowStatus.CRAWLED, "")

                if not self.image_one(row):
                    self.update_status(row_id, RowStatus.FAILED, "image_failed")
                    result.rows.append(PipelineRowResult(row_id=row_id, status=RowStatus.FAILED, error="image_failed"))
                    continue
                self.update_status(row_id, RowStatus.IMAGE_DONE, "")

                if not self.upload_one(row):
                    self.update_status(row_id, RowStatus.FAILED, "upload_failed")
                    result.rows.append(PipelineRowResult(row_id=row_id, status=RowStatus.FAILED, error="upload_failed"))
                    continue
                self.update_status(row_id, RowStatus.UPLOADED, "")
                result.rows.append(PipelineRowResult(row_id=row_id, status=RowStatus.UPLOADED))
            except Exception as exc:
                self.update_status(row_id, RowStatus.FAILED, str(exc))
                result.rows.append(PipelineRowResult(row_id=row_id, status=RowStatus.FAILED, error=str(exc)))
                # never raise: continue next row
                continue
        return result

