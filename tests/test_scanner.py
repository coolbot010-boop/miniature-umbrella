import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scanner  # noqa: E402

MARKETS = [
    {"market": m, "status": "trading", "minOrderInQuoteAsset": "5", "minOrderInBaseAsset": "0.001"}
    for m in ("GOOD-EUR", "FLAT-EUR", "THIN-EUR", "WIDE-EUR", "USDC-EUR", "PUMP-EUR", "GOOD-BTC")
] + [{"market": "HALT-EUR", "status": "halted"}]


def tick(m, last=10.0, open_=9.5, vol=1e6, bid=9.99, ask=10.0):
    return {"market": m, "last": str(last), "open": str(open_), "volumeQuote": str(vol),
            "bid": str(bid), "ask": str(ask)}


TICKERS = [
    tick("GOOD-EUR"), tick("FLAT-EUR"),
    tick("THIN-EUR", vol=10_000),             # te weinig handel
    tick("WIDE-EUR", bid=9.5, ask=10.0),      # spread 5%
    tick("USDC-EUR"),                         # stablecoin
    tick("PUMP-EUR", last=20.0, open_=10.0),  # vandaag +100%
    tick("GOOD-BTC"), tick("HALT-EUR"),
]


def api_get(path, params=None):
    return {"markets": MARKETS, "ticker/24h": TICKERS}[path]


def candles(market, interval, limit=100, end_ms=None):
    if market == "GOOD-EUR":   # rustig omhoog
        closes = [10 * (1.002 ** i) * (1 + 0.001 * (-1) ** i) for i in range(100)]
    else:                      # zijwaarts
        closes = [10 * (1 + 0.003 * (-1) ** i) for i in range(100)]
    return [[i, 0, 0, 0, c, 0] for i, c in enumerate(closes)]


class ScannerTest(unittest.TestCase):
    def setUp(self):
        scanner._markets_cache.update(t=0, data={})
        p1 = mock.patch.object(scanner.bot, "api_get", api_get)
        p2 = mock.patch.object(scanner.bot, "get_candles", candles)
        p1.start(); p2.start()
        self.addCleanup(p1.stop); self.addCleanup(p2.stop)

    def test_filters_illiquid_wide_stable_halted_and_non_eur(self):
        names = {c["market"] for c in scanner.candidates()}
        self.assertEqual(names, {"GOOD-EUR", "FLAT-EUR", "PUMP-EUR"})

    def test_ranks_uptrend_first_and_skips_pumped(self):
        ranked = scanner.scan()
        self.assertEqual([r["market"] for r in ranked], ["GOOD-EUR", "FLAT-EUR"])
        self.assertTrue(ranked[0]["uptrend"])

    def test_quantity_decimals_fallback(self):
        self.assertEqual(scanner.quantity_decimals("GOOD-EUR"), 3)


if __name__ == "__main__":
    unittest.main()
