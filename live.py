"""Echt handelen op Bitvavo met de API-key uit .env.

Veiligheid:
- De bot houdt een eigen boekhouding bij (live_state.json) en zet nooit meer
  in dan LIVE_BUDGET_EUR. Hij verkoopt alleen munten die hij zelf gekocht heeft,
  dus crypto die je al had blijft onaangeroerd.
- Zakt de waarde onder LIVE_BUDGET_EUR - LIVE_MAX_LOSS_EUR, dan stopt hij.
- Maximaal LIVE_MAX_TRADES_PER_DAY orders per dag.
- Bij elke foutmelding van de beurs op een order stopt de bot direct.
"""

import hashlib
import hmac
import json
import math
import os
import time
import urllib.error
import urllib.request
from datetime import date

import bot
import config

LIVE_STATE_FILE = "live_state.json"
LIVE_TRADES_FILE = "live_trades.csv"


def load_env(path=".env"):
    env = {}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    return env


class Bitvavo:
    def __init__(self, key, secret):
        self.key, self.secret = key, secret

    def request(self, method, path, params=None, body=None):
        query = ("?" + bot.urllib.parse.urlencode(params)) if params else ""
        url_path = f"/v2/{path}{query}"
        payload = json.dumps(body, separators=(",", ":")) if body else ""
        ts = str(int(time.time() * 1000))
        sig = hmac.new(self.secret.encode(), (ts + method + url_path + payload).encode(),
                       hashlib.sha256).hexdigest()
        req = urllib.request.Request(
            "https://api.bitvavo.com" + url_path, data=payload.encode() or None, method=method,
            headers={
                "Bitvavo-Access-Key": self.key,
                "Bitvavo-Access-Signature": sig,
                "Bitvavo-Access-Timestamp": ts,
                "Bitvavo-Access-Window": "10000",
                "Content-Type": "application/json",
                "User-Agent": "trade-bot",
            })
        try:
            with urllib.request.urlopen(req, timeout=15, context=bot.SSL_CONTEXT) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Bitvavo {e.code}: {e.read().decode(errors='replace')}") from None

    def balance(self, symbol):
        rows = self.request("GET", "balance", {"symbol": symbol})
        return float(rows[0]["available"]) if rows else 0.0

    def order(self, market, side, **amount):
        body = {"market": market, "side": side, "orderType": "market",
                "operatorId": config.OPERATOR_ID, **amount}
        result = self.request("POST", "order", body=body)
        # Een marktorder is normaal direct gevuld; zo niet, even nakijken
        for _ in range(10):
            if result.get("status") in ("filled", "canceled", "cancelled", "rejected", "expired"):
                break
            time.sleep(1)
            result = self.request("GET", "order", {"market": market, "orderId": result["orderId"]})
        return result


def quantity_decimals(market):
    info = bot.api_get("markets", {"market": market})
    return int(info.get("quantityDecimals", 8))


def floor_to(x, decimals):
    f = 10 ** decimals
    return math.floor(x * f) / f


def fill_summary(result, side, base):
    """Vertaal een orderresultaat naar (munten, eur, kosten_eur)."""
    coins = float(result.get("filledAmount", 0))
    quote = float(result.get("filledAmountQuote", 0))
    fee = float(result.get("feePaid", 0))
    fee_cur = result.get("feeCurrency", "EUR")
    if fee_cur == base:          # kosten in munten ingehouden
        fee_eur = fee * (quote / coins if coins else 0)
        coins = coins - fee if side == "buy" else coins
        eur = quote
    else:                        # kosten in euro's
        fee_eur = fee
        eur = quote + fee if side == "buy" else quote - fee
    return coins, eur, fee_eur


def load_state():
    if os.path.exists(LIVE_STATE_FILE):
        with open(LIVE_STATE_FILE) as f:
            data = json.load(f)
    else:
        data = {}
    p = bot.Portfolio(**data.get("portfolio", {"eur": config.LIVE_BUDGET_EUR}))
    return p, data.get("day", ""), data.get("trades_today", 0)


def save_state(p, day, trades_today):
    with open(LIVE_STATE_FILE, "w") as f:
        json.dump({"portfolio": bot.asdict(p), "day": day, "trades_today": trades_today}, f, indent=2)


def client_from_env():
    env = {**load_env(), **os.environ}
    key, secret = env.get("BITVAVO_API_KEY"), env.get("BITVAVO_API_SECRET")
    if not key or not secret:
        raise SystemExit("Geen API-key gevonden. Kopieer .env.example naar .env en vul hem in.")
    return Bitvavo(key, secret)


def cmd_check():
    """Alleen lezen: test of de key werkt. Plaatst geen orders."""
    c = client_from_env()
    base, quote = config.MARKET.split("-")
    print(f"API-key werkt. Beschikbaar: €{c.balance(quote):.2f} en {c.balance(base):.8f} {base}")
    p, _, _ = load_state()
    print(f"Boekhouding bot: €{p.eur:.2f} en {p.coins:.8f} {base} (budget €{config.LIVE_BUDGET_EUR:.2f})")


def cmd_live():
    if config.OPERATOR_ID is None:
        raise SystemExit("Zet eerst OPERATOR_ID in config.py (een getal naar keuze, bijv. 1001).")
    c = client_from_env()
    base, quote = config.MARKET.split("-")
    decimals = quantity_decimals(config.MARKET)
    p, day, trades_today = load_state()
    floor = config.LIVE_BUDGET_EUR - config.LIVE_MAX_LOSS_EUR
    target = config.LIVE_BUDGET_EUR + config.LIVE_PROFIT_TARGET_EUR

    print("=" * 60)
    print("LET OP: ECHT GELD")
    print(f"Markt {config.MARKET}, budget €{config.LIVE_BUDGET_EUR:.2f}, "
          f"stopt bij waarde < €{floor:.2f} of > €{target:.2f}, max {config.LIVE_MAX_TRADES_PER_DAY} orders/dag")
    print(f"Boekhouding: €{p.eur:.2f} + {p.coins:.8f} {base}")
    print("=" * 60)
    if input("Typ 'ja' om te starten: ").strip().lower() != "ja":
        print("Afgebroken.")
        return

    if config.DASHBOARD:
        import dashboard
        dashboard.start_background("live")

    step = bot.INTERVAL_MS[config.INTERVAL]
    bid = ask = 0.0
    closes = []

    def status(reason, stopped=None):
        if bid:
            bot.write_status("live", p, bid, ask, closes, reason, config.LIVE_BUDGET_EUR,
                             floor, target, stopped)

    while True:
        try:
            if day != date.today().isoformat():
                day, trades_today = date.today().isoformat(), 0

            candles = bot.get_candles(config.MARKET, config.INTERVAL, limit=config.SLOW_SMA + 5)
            now_ms = int(time.time() * 1000)
            closes = [c_[4] for c_ in candles if c_[0] + step <= now_ms]
            bid, ask = bot.get_book(config.MARKET)
            value = p.value(bid)

            # Verliesgrens of winstdoel: alles verkopen en stoppen
            stop = None
            if value <= floor:
                stop = f"verliesgrens bereikt (waarde €{value:.2f})"
            elif value >= target:
                stop = f"winstdoel bereikt (waarde €{value:.2f})"

            if stop:
                action, reason = ("sell" if p.in_position else None), stop
            else:
                action, reason = bot.decide(closes, p, bid if p.in_position else ask)
            if action and not stop and trades_today >= config.LIVE_MAX_TRADES_PER_DAY:
                print(f"[{bot.now()}] {action} overgeslagen: daglimiet bereikt")
                action = None

            if action == "buy":
                spend = floor_to(min(p.eur, config.MAX_PER_TRADE_EUR, c.balance(quote)), 2)
                if spend >= config.MIN_ORDER_EUR:
                    res = c.order(config.MARKET, "buy", amountQuote=f"{spend:.2f}")
                    coins, eur, fee = fill_summary(res, "buy", base)
                    p.eur -= eur
                    p.coins += coins
                    p.entry_price = eur / coins if coins else ask
                    record(p, "buy", res, coins, eur, fee, reason, bid)
                    trades_today += 1
            elif action == "sell":
                amount = floor_to(min(p.coins, c.balance(base)), decimals)
                if amount > 0:
                    pnl = (bid / p.entry_price - 1) * 100 if p.entry_price else 0
                    res = c.order(config.MARKET, "sell", amount=f"{amount:.{decimals}f}")
                    coins, eur, fee = fill_summary(res, "sell", base)
                    p.eur += eur
                    p.coins = max(0.0, p.coins - coins)
                    if p.coins * bid < 1:  # stofrestje: positie is dicht
                        p.coins, p.entry_price = 0.0, 0.0
                    record(p, "sell", res, coins, eur, fee, f"{reason} ({pnl:+.2f}%)", bid)
                    trades_today += 1

            save_state(p, day, trades_today)
            status(reason, stop)
            print(f"[{bot.now()}] koers €{(bid + ask) / 2:.2f} | waarde €{p.value(bid):.2f} | {reason}")
            if stop:
                print(f"[{bot.now()}] {stop}. Alles staat weer in euro's. Bot stopt.")
                return
        except KeyboardInterrupt:
            raise
        except RuntimeError as e:  # fout van de beurs bij een order: niet doorgaan
            save_state(p, day, trades_today)
            status(f"beursfout: {e}", f"beursfout: {e}")
            print(f"[{bot.now()}] Beursfout, bot stopt voor de veiligheid: {e}")
            return
        except Exception as e:  # netwerk hikt: later opnieuw
            print(f"[{bot.now()}] fout: {e}")
        time.sleep(config.POLL_SECONDS)


def record(p, side, res, coins, eur, fee, reason, price):
    p.fees_paid += fee
    p.trades += 1
    trade = {"side": side, "price": eur / coins if coins else 0, "amount": coins,
             "eur": eur, "fee": fee, "reason": f"{reason} [{res.get('status')}]"}
    bot.log_trade(trade, p, price, LIVE_TRADES_FILE)
    print(f"[{bot.now()}] ECHT {side.upper()}: {coins:.8f} voor €{eur:.2f} "
          f"(kosten €{fee:.4f}) — {reason}")
