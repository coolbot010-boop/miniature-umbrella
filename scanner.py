"""Scanner: zoekt op alle euro-markten van Bitvavo de beste coin om te kopen.

Stappen:
1. Alle EUR-markten ophalen die nu verhandelbaar zijn (geen stablecoins).
2. Rommel eruit: te weinig handel per dag of te groot verschil tussen koop- en
   verkoopprijs (dat verschil betaal je bij elke trade extra).
3. Van de meest verhandelde coins de 15-minuten-candles bekijken en een score
   geven: hoe hard stijgt hij de laatste 4 uur, gedeeld door hoe wild hij
   beweegt, plus een bonus als de trend omhoog wijst.
4. Coins die vandaag al extreem gepompt zijn (meer dan SCAN_MAX_PUMP) slaat hij
   over: daar koop je meestal de top.
"""

import math
import time

import bot
import config

STABLECOINS = {"USDT", "USDC", "EURC", "EUROC", "DAI", "EURS", "PYUSD", "TUSD",
               "FDUSD", "USDE", "USDS", "BUSD", "EURI", "EURQ", "USDQ", "RLUSD"}

_markets_cache = {"t": 0, "data": {}}


def markets():
    """Info per markt (minimale order, decimalen), 1 uur gecachet."""
    if time.time() - _markets_cache["t"] > 3600 or not _markets_cache["data"]:
        rows = bot.api_get("markets")
        _markets_cache.update(t=time.time(), data={r["market"]: r for r in rows})
    return _markets_cache["data"]


def quantity_decimals(market):
    """Hoeveel decimalen Bitvavo toestaat voor de hoeveelheid munten."""
    info = markets().get(market, {})
    if info.get("quantityDecimals") is not None:
        return int(info["quantityDecimals"])
    step = str(info.get("minOrderInBaseAsset", ""))
    if "." in step:
        return len(step.split(".")[1].rstrip("0")) or 0
    return 8 if not step else 0


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def candidates():
    """Stap 1 en 2: liquide EUR-markten met een kleine spread."""
    info = markets()
    out = []
    for t in bot.api_get("ticker/24h"):
        m = t.get("market", "")
        meta = info.get(m, {})
        base, _, quote = m.partition("-")
        if quote != "EUR" or base in STABLECOINS or meta.get("status") != "trading":
            continue
        bid, ask, last, open_ = _f(t.get("bid")), _f(t.get("ask")), _f(t.get("last")), _f(t.get("open"))
        volume = _f(t.get("volumeQuote"))
        if not (bid and ask and last and open_ and volume) or ask < bid:
            continue
        spread = (ask - bid) / ((ask + bid) / 2)
        if volume < config.SCAN_MIN_VOLUME_EUR or spread > config.SCAN_MAX_SPREAD:
            continue
        out.append({"market": m, "bid": bid, "ask": ask, "volume_eur": volume,
                    "spread": spread, "ret_24h": last / open_ - 1,
                    "min_order_eur": _f(meta.get("minOrderInQuoteAsset")) or config.MIN_ORDER_EUR})
    out.sort(key=lambda c: c["volume_eur"], reverse=True)
    return out[:config.SCAN_TOP_N]


def score(closes):
    """Momentum per eenheid risico, plus bonus voor een opwaartse trend."""
    if len(closes) < 50:
        return None
    rets = [closes[i] / closes[i - 1] - 1 for i in range(len(closes) - 48, len(closes))]
    mean = sum(rets) / len(rets)
    vol = math.sqrt(sum((r - mean) ** 2 for r in rets) / len(rets)) or 1e-9
    ret_4h = closes[-1] / closes[-17] - 1
    ret_1h = closes[-1] / closes[-5] - 1
    fast, slow = bot.sma(closes, config.FAST_SMA), bot.sma(closes, config.SLOW_SMA)
    uptrend = fast > slow and closes[-1] > slow
    s = ret_4h / (vol * 4) + (0.5 if uptrend else 0.0)
    return {"score": s, "ret_1h": ret_1h, "ret_4h": ret_4h, "volatility": vol, "uptrend": uptrend}


def scan():
    """Geeft alle beoordeelde coins, beste eerst."""
    ranked = []
    for c in candidates():
        if c["ret_24h"] > config.SCAN_MAX_PUMP:
            continue
        try:
            closes = [k[4] for k in bot.get_candles(c["market"], "15m", limit=100)]
        except Exception:
            continue
        s = score(closes)
        if s:
            ranked.append({**c, **s})
    ranked.sort(key=lambda c: c["score"], reverse=True)
    return ranked
