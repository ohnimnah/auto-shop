import unittest

from app.jobs.row_status import RowStatus


class RowStatusTests(unittest.TestCase):
    def test_status_order(self):
        flow = [RowStatus.NEW, RowStatus.CRAWLED, RowStatus.IMAGE_DONE, RowStatus.UPLOADED]
        self.assertEqual(flow[0].value, "신규")
        self.assertEqual(flow[-1].value, "업로드완료")
        self.assertNotIn(RowStatus.FAILED, flow)


if __name__ == "__main__":
    unittest.main()

