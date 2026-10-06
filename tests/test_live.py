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
    """Simuleert Bitvavo: vult marktorders met 0,25% kosten in EUR, per markt een koers."""

    def __init__(self, eur=100.0, own=None):
        self.bal = {"EUR": eur, **(own or {})}
        self.prices = {}
        self.orders = []

    def balance(self, symbol):
        return self.bal.get(symbol, 0.0)

    def order(self, market, side, **amount):
        base = market.split("-")[0]
        price = self.prices[market]
        self.orders.append((side, market, amount))
        if side == "buy":
            quote = float(amount["amountQuote"])
            fee = quote * 0.0025
            coins = (quote - fee) / price
            self.bal["EUR"] -= quote
            self.bal[base] = self.bal.get(base, 0) + coins
            return {"status": "filled", "filledAmount": str(coins),
                    "filledAmountQuote": str(quote - fee), "feePaid": str(fee), "feeCurrency": "EUR"}
        coins = float(amount["amount"])
        quote = coins * price
        fee = quote * 0.0025
        self.bal[base] -= coins
        self.bal["EUR"] += quote - fee
        return {"status": "filled", "filledAmount": str(coins),
                "filledAmountQuote": str(quote), "feePaid": str(fee), "feeCurrency": "EUR"}


class SignatureTest(unittest.TestCase):
    def test_signature_is_hmac_of_ts_method_path_body(self):
        c = live.Bitvavo("k", "secret")
        c.offset_ms = 0
        captured = {}

        def fake_urlopen(req, timeout, context=None):
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


class ClockTest(unittest.TestCase):
    def test_uses_bitvavo_clock_when_pc_clock_is_wrong(self):
        c = live.Bitvavo("k", "s")
        with mock.patch.object(live.bot, "api_get", return_value={"time": 2_000_000}), \
                mock.patch.object(live.time, "time", return_value=1_000.0):
            self.assertEqual(c.now_ms(), 2_000_000)


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


def choice(market, price):
    return {"market": market, "bid": price, "ask": price, "min_order_eur": 5.0, "score": 1.0,
            "ret_1h": 0.01, "ret_4h": 0.02, "ret_24h": 0.03, "volume_eur": 1e6,
            "spread": 0.001, "uptrend": True}


class LiveLoopTest(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        os.chdir(tempfile.mkdtemp())

    def tearDown(self):
        os.chdir(self.cwd)

    def run_loop(self, ex, path, minutes, scan_result=None):
        """Draai de live-loop; path(min) geeft per minuut de koersen {markt: prijs}."""
        clock = {"min": 0}
        t0 = 1_800_000_000.0

        def fake_time():
            return t0 + clock["min"] * 60

        def book(market):
            p = ex.prices[market]
            return p, p

        def scan():
            ex.prices.update(path(clock["min"]))
            return scan_result(clock["min"]) if scan_result else \
                [choice(m, pr) for m, pr in path(clock["min"]).items()]

        def sleep(_):
            clock["min"] += 1
            ex.prices.update(path(clock["min"]))
            if clock["min"] >= minutes:
                raise KeyboardInterrupt

        ex.prices.update(path(0))
        import scanner
        with mock.patch.object(live, "client_from_env", return_value=ex), \
                mock.patch.object(scanner, "scan", scan), \
                mock.patch.object(scanner, "quantity_decimals", return_value=8), \
                mock.patch.object(bot, "get_book", book), \
                mock.patch.object(live.time, "time", fake_time), \
                mock.patch.object(live.time, "sleep", sleep), \
                mock.patch.object(config, "OPERATOR_ID", 1001), \
                mock.patch.object(config, "DASHBOARD", False), \
                mock.patch.object(builtins, "input", return_value="ja"), \
                mock.patch("builtins.print"):
            try:
                live.cmd_live()
            except KeyboardInterrupt:
                pass
        return live.load_state()

    def test_buys_immediately_at_start(self):
        ex = FakeExchange()
        self.run_loop(ex, lambda m: {"AAA-EUR": 10.0}, 2)
        self.assertEqual(ex.orders[0][:2], ("buy", "AAA-EUR"))
        self.assertEqual(float(ex.orders[0][2]["amountQuote"]), config.LIVE_BUDGET_EUR)

    def test_sells_after_hold_time_without_profit_and_buys_next(self):
        ex = FakeExchange()
        prices = lambda m: {"AAA-EUR": 10.0, "BBB-EUR": 5.0}
        st = self.run_loop(ex, prices, config.HOLD_MINUTES + 2)
        sides = [(o[0], o[1]) for o in ex.orders]
        self.assertEqual(sides[0], ("buy", "AAA-EUR"))
        self.assertEqual(sides[1], ("sell", "AAA-EUR"))
        # verloren op AAA -> volgende keer een andere coin
        self.assertEqual(sides[2], ("buy", "BBB-EUR"))
        self.assertEqual(st["market"], "BBB-EUR")

    def test_no_sale_before_hold_time_when_not_crashing(self):
        ex = FakeExchange()
        self.run_loop(ex, lambda m: {"AAA-EUR": 10.0 * (1 - 0.01 * m)}, config.HOLD_MINUTES - 1)
        self.assertEqual([o[0] for o in ex.orders], ["buy"])

    def test_stop_loss_at_minus_50_percent_sells_immediately(self):
        ex = FakeExchange()
        self.run_loop(ex, lambda m: {"AAA-EUR": 10.0 if m < 3 else 4.9}, 5)
        self.assertEqual([o[0] for o in ex.orders][:2], ["buy", "sell"])
        self.assertEqual(ex.orders[1][1], "AAA-EUR")

    def test_winner_keeps_running_and_sells_20_percent_below_peak(self):
        # stijgt tot +100% in 40 min, zakt daarna 1% per minuut
        def path(m):
            p = 10.0 * (1 + m / 40) if m <= 40 else 20.0 * (1 - 0.01 * (m - 40))
            return {"AAA-EUR": p}
        ex = FakeExchange(eur=50.0)
        sold = []
        real_order = ex.order

        def order(market, side, **amount):
            if side == "sell":
                sold.append(ex.prices[market])
            return real_order(market, side, **amount)
        ex.order = order
        self.run_loop(ex, path, 70)
        # niet verkocht tijdens de stijging, wel zodra hij 20% onder de piek (20) zakt
        self.assertTrue(sold)
        self.assertAlmostEqual(sold[0], 16.0, delta=0.21)

    def test_never_spends_more_than_budget_or_sells_users_own_coins(self):
        ex = FakeExchange(eur=500.0, own={"AAA": 3.0})
        prices = lambda m: {"AAA-EUR": 10.0, "BBB-EUR": 5.0}
        self.run_loop(ex, prices, 60)
        for side, _, amt in ex.orders:
            if side == "buy":
                self.assertLessEqual(float(amt["amountQuote"]), config.LIVE_BUDGET_EUR)
        self.assertGreaterEqual(ex.bal["AAA"], 3.0 - 1e-9)
        self.assertGreaterEqual(ex.bal["EUR"], 500 - config.LIVE_BUDGET_EUR - 1e-9)

    def test_daily_order_cap_blocks_buys_not_sells(self):
        ex = FakeExchange()
        with mock.patch.object(config, "LIVE_MAX_TRADES_PER_DAY", 3):
            st = self.run_loop(ex, lambda m: {"AAA-EUR": 10.0, "BBB-EUR": 5.0}, 60)
        self.assertEqual(len(ex.orders), 4)  # koop, verkoop, koop, verkoop
        self.assertFalse(st["portfolio"].in_position)

    def test_stops_at_max_loss(self):
        ex = FakeExchange()
        with open(live.LIVE_STATE_FILE, "w") as f:
            json.dump({"portfolio": {"eur": config.LIVE_BUDGET_EUR - config.LIVE_MAX_LOSS_EUR - 1}}, f)
        self.run_loop(ex, lambda m: {"AAA-EUR": 10.0}, 5)
        self.assertEqual(ex.orders, [])

    def test_old_btc_state_is_migrated(self):
        with open(live.LIVE_STATE_FILE, "w") as f:
            json.dump({"portfolio": {"eur": 0.0, "coins": 0.001, "entry_price": 50000.0}}, f)
        st = live.load_state()
        self.assertEqual(st["market"], "BTC-EUR")
        self.assertEqual(st["peak"], 50000.0)

    def test_refuses_without_confirmation(self):
        ex = FakeExchange()
        with mock.patch.object(live, "client_from_env", return_value=ex), \
                mock.patch.object(config, "OPERATOR_ID", 1001), \
                mock.patch.object(builtins, "input", return_value="nee"), \
                mock.patch("builtins.print"):
            live.cmd_live()
        self.assertEqual(ex.orders, [])


if __name__ == "__main__":
    unittest.main()
