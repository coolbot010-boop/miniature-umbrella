import builtins
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot  # noqa: E402
import config  # noqa: E402
import live  # noqa: E402


class FakeExchange:
    """Simuleert Bitvavo: vult marktorders met 0,25% kosten in EUR."""

    def __init__(self, eur=100.0, btc=0.5):
        self.bal = {"EUR": eur, "BTC": btc}
        self.price = 100.0
        self.orders = []

    def balance(self, symbol):
        return self.bal[symbol]

    def order(self, market, side, **amount):
        self.orders.append((side, amount))
        if side == "buy":
            quote = float(amount["amountQuote"])
            fee = quote * 0.0025
            coins = (quote - fee) / self.price
            self.bal["EUR"] -= quote
            self.bal["BTC"] += coins
            return {"status": "filled", "filledAmount": str(coins),
                    "filledAmountQuote": str(quote - fee), "feePaid": str(fee), "feeCurrency": "EUR"}
        coins = float(amount["amount"])
        quote = coins * self.price
        fee = quote * 0.0025
        self.bal["BTC"] -= coins
        self.bal["EUR"] += quote - fee
        return {"status": "filled", "filledAmount": str(coins),
                "filledAmountQuote": str(quote), "feePaid": str(fee), "feeCurrency": "EUR"}


class SignatureTest(unittest.TestCase):
    def test_signature_is_hmac_of_ts_method_path_body(self):
        c = live.Bitvavo("k", "secret")
        captured = {}

        def fake_urlopen(req, timeout):
            captured["req"] = req
            raise live.urllib.error.URLError("stop")

        with mock.patch.object(live.urllib.request, "urlopen", fake_urlopen), \
                mock.patch.object(live.time, "time", return_value=1.0):
            with self.assertRaises(live.urllib.error.URLError):
                c.request("POST", "order", body={"market": "BTC-EUR", "operatorId": 1})
        h = {k.lower(): v for k, v in captured["req"].header_items()}
        body = '{"market":"BTC-EUR","operatorId":1}'
        expect = hmac.new(b"secret", ("1000POST/v2/order" + body).encode(), hashlib.sha256).hexdigest()
        self.assertEqual(h["bitvavo-access-signature"], expect)
        self.assertEqual(h["bitvavo-access-timestamp"], "1000")
        self.assertEqual(captured["req"].data, body.encode())
        self.assertEqual(json.loads(captured["req"].data)["operatorId"], 1)


class FillTest(unittest.TestCase):
    def test_buy_fee_in_eur(self):
        coins, eur, fee = live.fill_summary(
            {"filledAmount": "0.1", "filledAmountQuote": "9.975", "feePaid": "0.025",
             "feeCurrency": "EUR"}, "buy", "BTC")
        self.assertAlmostEqual(coins, 0.1)
        self.assertAlmostEqual(eur, 10.0)
        self.assertAlmostEqual(fee, 0.025)

    def test_sell_fee_in_eur(self):
        coins, eur, fee = live.fill_summary(
            {"filledAmount": "0.1", "filledAmountQuote": "10", "feePaid": "0.025",
             "feeCurrency": "EUR"}, "sell", "BTC")
        self.assertAlmostEqual(eur, 9.975)


class LiveLoopTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.dir)

    def tearDown(self):
        os.chdir(self.cwd)

    def run_loop(self, ex, prices, ticks):
        """Draai de live-loop met nep-beurs en nep-koersen."""
        state = {"i": 0}

        def candles(market, interval, limit=100, end_ms=None):
            i = state["i"]
            t = int(time.time() * 1000) - 900_000 * (i + 2)
            return [[t + k * 900_000, 0, 0, 0, prices[k], 0] for k in range(i + 1)] + \
                   [[int(time.time() * 1000), 0, 0, 0, 0, 0]]

        def book(market):
            ex.price = prices[state["i"]]
            return ex.price, ex.price

        def sleep(_):
            state["i"] += 1
            if state["i"] >= ticks:
                raise KeyboardInterrupt

        with mock.patch.object(live, "client_from_env", return_value=ex), \
                mock.patch.object(live, "quantity_decimals", return_value=8), \
                mock.patch.object(bot, "get_candles", candles), \
                mock.patch.object(bot, "get_book", book), \
                mock.patch.object(live.time, "sleep", sleep), \
                mock.patch.object(config, "OPERATOR_ID", 1001), \
                mock.patch.object(builtins, "input", return_value="ja"), \
                mock.patch.object(config, "DASHBOARD", False), \
                mock.patch("builtins.print"):
            try:
                live.cmd_live()
            except KeyboardInterrupt:
                pass
        return live.load_state()[0]

    def test_buys_within_budget_and_never_sells_users_own_coins(self):
        ex = FakeExchange(eur=100.0, btc=0.5)   # gebruiker had al 0.5 BTC
        prices = [100 - i * 0.5 for i in range(30)] + [85 + i * 2 for i in range(15)] \
            + [113 - i * 3 for i in range(15)]
        p = self.run_loop(ex, prices, len(prices))
        buys = [o for o in ex.orders if o[0] == "buy"]
        self.assertTrue(buys)
        for _, amt in buys:
            self.assertLessEqual(float(amt["amountQuote"]), config.LIVE_BUDGET_EUR)
        # Eigen 0.5 BTC van de gebruiker blijft staan
        self.assertGreaterEqual(ex.bal["BTC"], 0.5 - 1e-9)
        # EUR die de bot uitgaf is nooit meer dan het budget
        self.assertGreaterEqual(ex.bal["EUR"], 100 - config.LIVE_BUDGET_EUR - 1e-9)
        self.assertAlmostEqual(p.value(prices[-1]) - p.eur - p.coins * prices[-1], 0)

    def test_stops_at_max_loss(self):
        ex = FakeExchange()
        with open(live.LIVE_STATE_FILE, "w") as f:
            json.dump({"portfolio": {"eur": config.LIVE_BUDGET_EUR - config.LIVE_MAX_LOSS_EUR - 1}}, f)
        self.run_loop(ex, [100.0] * 40, 40)
        self.assertEqual(ex.orders, [])

    def test_sells_everything_and_stops_at_profit_target(self):
        ex = FakeExchange()
        budget = config.LIVE_BUDGET_EUR
        coins = budget / 100
        with open(live.LIVE_STATE_FILE, "w") as f:
            json.dump({"portfolio": {"eur": 0.0, "coins": coins, "entry_price": 100.0}}, f)
        price = (budget + config.LIVE_PROFIT_TARGET_EUR) / coins + 1
        p = self.run_loop(ex, [price] * 40, 40)
        self.assertEqual([o[0] for o in ex.orders], ["sell"])
        self.assertEqual(p.coins, 0)
        self.assertGreater(p.eur, budget + config.LIVE_PROFIT_TARGET_EUR * 0.99)

    def test_sells_everything_and_stops_at_max_loss(self):
        ex = FakeExchange()
        budget = config.LIVE_BUDGET_EUR
        coins = budget / 100
        with open(live.LIVE_STATE_FILE, "w") as f:
            json.dump({"portfolio": {"eur": 0.0, "coins": coins, "entry_price": 100.0}}, f)
        price = (budget - config.LIVE_MAX_LOSS_EUR) / coins - 1
        p = self.run_loop(ex, [price] * 40, 40)
        self.assertEqual([o[0] for o in ex.orders], ["sell"])
        self.assertEqual(p.coins, 0)

    def test_refuses_without_confirmation(self):
        ex = FakeExchange()
        with mock.patch.object(live, "client_from_env", return_value=ex), \
                mock.patch.object(live, "quantity_decimals", return_value=8), \
                mock.patch.object(config, "OPERATOR_ID", 1001), \
                mock.patch.object(builtins, "input", return_value="nee"), \
                mock.patch("builtins.print"):
            live.cmd_live()
        self.assertEqual(ex.orders, [])


if __name__ == "__main__":
    unittest.main()
