import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot  # noqa: E402
import dashboard  # noqa: E402


class DashboardTest(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        os.chdir(tempfile.mkdtemp())

    def tearDown(self):
        os.chdir(self.cwd)

    def test_status_written_by_bot_reaches_dashboard(self):
        p = bot.Portfolio(eur=30.0, coins=0.0004, entry_price=50000.0, fees_paid=0.05, trades=1)
        closes = [50000.0 + i for i in range(30)]
        bot.write_status("live", p, 50000.0, 50010.0, closes, "wachten", 50.0, 25.0, 100.0)
        with mock.patch.object(dashboard, "candles", return_value=[]):
            d = dashboard.data("live")
        self.assertTrue(d["running"])
        self.assertAlmostEqual(d["status"]["value"], 30.0 + 0.0004 * 50000)
        self.assertEqual(d["status"]["target"], 100.0)
        self.assertEqual(len(d["history"]), 1)
        json.dumps(d)

    def test_stopped_bot_not_shown_as_running(self):
        p = bot.Portfolio(eur=50.0)
        bot.write_status("live", p, 1.0, 1.0, [], "x", 50.0, 25.0, 100.0, stopped="winstdoel")
        with mock.patch.object(dashboard, "candles", return_value=[]):
            self.assertFalse(dashboard.data("live")["running"])

    def test_empty_state(self):
        with mock.patch.object(dashboard, "candles", return_value=[]):
            d = dashboard.data("paper")
        self.assertIsNone(d["status"])
        self.assertFalse(d["running"])


if __name__ == "__main__":
    unittest.main()
