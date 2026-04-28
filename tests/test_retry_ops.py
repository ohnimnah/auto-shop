import unittest

from marketplace.buyma.retry_ops import safe_click, safe_send_keys


class _ClickTarget:
    def __init__(self):
        self.calls = 0

    def click(self):
        self.calls += 1


class _FailingClickTarget:
    def click(self):
        raise RuntimeError("fail")


class _Driver:
    def __init__(self):
        self.clicked = False

    def execute_script(self, _script, _target):
        self.clicked = True


class _Input:
    def __init__(self):
        self.values = []

    def send_keys(self, v):
        self.values.append(v)


class RetryOpsTests(unittest.TestCase):
    def test_safe_click_success(self):
        d = _Driver()
        t = _ClickTarget()
        safe_click(d, t)
        self.assertEqual(t.calls, 1)

    def test_safe_click_fallback_js(self):
        d = _Driver()
        t = _FailingClickTarget()
        safe_click(d, t)
        self.assertTrue(d.clicked)

    def test_safe_send_keys(self):
        i = _Input()
        safe_send_keys(i, "abc")
        self.assertEqual(i.values, ["abc"])


if __name__ == "__main__":
    unittest.main()

