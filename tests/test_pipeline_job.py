import unittest

from app.jobs.pipeline_job import PipelineJob
from app.jobs.row_status import RowStatus


class PipelineJobTests(unittest.TestCase):
    def test_row_failure_is_isolated(self):
        statuses = []

        def update_status(row_id, status, error):
            statuses.append((row_id, status, error))

        rows = [{"row_num": 1}, {"row_num": 2}, {"row_num": 3}]
        job = PipelineJob(
            crawl_one=lambda row: row["row_num"] != 2,
            image_one=lambda _row: True,
            upload_one=lambda _row: True,
            update_status=update_status,
        )
        result = job.run(rows)
        self.assertEqual(len(result.rows), 3)
        self.assertEqual(result.rows[0].status, RowStatus.UPLOADED)
        self.assertEqual(result.rows[1].status, RowStatus.FAILED)
        self.assertEqual(result.rows[2].status, RowStatus.UPLOADED)

    def test_row_status_transition_order(self):
        emitted = []

        def update_status(row_id, status, _error):
            emitted.append((row_id, status))

        row = {"row_num": 10}
        job = PipelineJob(
            crawl_one=lambda _row: True,
            image_one=lambda _row: True,
            upload_one=lambda _row: True,
            update_status=update_status,
        )
        job.run([row])
        self.assertEqual(
            emitted,
            [
                (10, RowStatus.CRAWLED),
                (10, RowStatus.IMAGE_DONE),
                (10, RowStatus.UPLOADED),
            ],
        )


if __name__ == "__main__":
    unittest.main()

