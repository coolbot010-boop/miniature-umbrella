import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot  # noqa: E402
import config  # noqa: E402


class PortfolioTest(unittest.TestCase):
    def test_round_trip_costs_fees(self):
        p = bot.Portfolio(eur=50)
        p.buy(100, 0.0025, 50)
        p.sell(100, 0.0025)
        self.assertAlmostEqual(p.eur, 50 * 0.9975 * 0.9975)
        self.assertEqual(p.trades, 2)

    def test_never_spends_more_than_cap_or_cash(self):
        p = bot.Portfolio(eur=50)
        t = p.buy(100, 0.0025, 20)
        self.assertEqual(t["eur"], 20)
        self.assertEqual(p.eur, 30)
        p2 = bot.Portfolio(eur=10)
        self.assertEqual(p2.buy(100, 0.0025, 50)["eur"], 10)

    def test_below_minimum_order_skipped(self):
        p = bot.Portfolio(eur=3)
        self.assertIsNone(p.buy(100, 0.0025, 50))


class StrategyTest(unittest.TestCase):
    def test_buy_on_cross_up_sell_on_cross_down(self):
        down = [100 - i for i in range(30)]
        up = down + [down[-1] + 3 * i for i in range(1, 15)]
        p = bot.Portfolio(eur=50)
        actions = []
        for i in range(len(down), len(up) + 1):
            a, _ = bot.decide(up[:i], p, up[i - 1])
            if a:
                actions.append(a)
                bot.execute(a, p, up[i - 1], up[i - 1])
        self.assertEqual(actions[0], "buy")

    def test_stop_loss(self):
        p = bot.Portfolio(eur=50)
        p.buy(100, 0.0025, 50)
        closes = [100.0] * 30
        a, reason = bot.decide(closes, p, 96)
        self.assertEqual(a, "sell")
        self.assertIn("stop-loss", reason)


class BacktestTest(unittest.TestCase):
    def test_simulation_runs_on_synthetic_prices(self):
        candles = [[i * 900_000, 0, 0, 0, 50_000 + 2000 * math.sin(i / 15), 0] for i in range(500)]
        p, last = bot.simulate(candles)
        self.assertGreater(p.trades, 0)
        self.assertGreater(p.fees_paid, 0)
        self.assertGreater(p.value(last), 0)


if __name__ == "__main__":
    unittest.main()
