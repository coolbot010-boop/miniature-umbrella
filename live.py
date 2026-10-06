"""Echt handelen op Bitvavo met de API-key uit .env.

Veiligheid:
- De bot houdt een eigen boekhouding bij (live_state.json) en zet nooit meer
  in dan LIVE_BUDGET_EUR. Hij verkoopt alleen munten die hij zelf gekocht heeft,
  dus crypto die je al had blijft onaangeroerd.
- Zakt de waarde onder LIVE_BUDGET_EUR - LIVE_MAX_LOSS_EUR, dan stopt hij.
- Maximaal LIVE_MAX_TRADES_PER_DAY orders per dag (verkopen gaan altijd door).

Strategie (zie config.py):
- Scant alle euro-markten en koopt direct de coin met de beste score.
- Verkoopt direct bij POSITION_STOP_LOSS onder de aankoopprijs.
- Na HOLD_MINUTES: verkopen als hij niet in winst staat, anders laten lopen
  tot de koers TRAILING_STOP onder de hoogste koers zakt.
- Na een verkoop meteen de volgende beste coin kopen.
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
        self.offset_ms = None  # verschil tussen klok van Bitvavo en van deze pc

    def now_ms(self):
        """Tijd volgens Bitvavo, zodat een verkeerde pc-klok orders niet laat mislukken."""
        if self.offset_ms is None:
            try:
                server = int(bot.api_get("time")["time"])
                self.offset_ms = server - int(time.time() * 1000)
            except Exception:
                return int(time.time() * 1000)
        return int(time.time() * 1000) + self.offset_ms

    def request(self, method, path, params=None, body=None):
        query = ("?" + bot.urllib.parse.urlencode(params)) if params else ""
        url_path = f"/v2/{path}{query}"
        payload = json.dumps(body, separators=(",", ":")) if body else ""
        ts = str(self.now_ms())
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
    """Stand van de bot. Oude bestanden (alleen BTC) worden automatisch omgezet."""
    data = {}
    if os.path.exists(LIVE_STATE_FILE):
        with open(LIVE_STATE_FILE) as f:
            data = json.load(f)
    st = {
        "portfolio": bot.Portfolio(**data.get("portfolio", {"eur": config.LIVE_BUDGET_EUR})),
        "market": data.get("market") or config.MARKET,
        "peak": data.get("peak"),
        "opened_at": data.get("opened_at") or int(time.time() * 1000),
        "day": data.get("day", ""),
        "trades_today": data.get("trades_today", 0),
    }
    if st["portfolio"].in_position and st["peak"] is None:
        st["peak"] = st["portfolio"].entry_price
    return st


def save_state(st):
    out = {**st, "portfolio": bot.asdict(st["portfolio"])}
    tmp = LIVE_STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(out, f, indent=2)
    os.replace(tmp, LIVE_STATE_FILE)


def client_from_env():
    env = {**load_env(), **os.environ}
    key, secret = env.get("BITVAVO_API_KEY"), env.get("BITVAVO_API_SECRET")
    if not key or not secret:
        raise SystemExit("Geen API-key gevonden. Kopieer .env.example naar .env en vul hem in.")
    return Bitvavo(key, secret)


def cmd_check():
    """Alleen lezen: test of de key werkt. Plaatst geen orders."""
    c = client_from_env()
    st = load_state()
    p, base = st["portfolio"], st["market"].split("-")[0]
    print(f"API-key werkt. Beschikbaar: €{c.balance('EUR'):.2f}")
    print(f"Boekhouding bot: €{p.eur:.2f}" + (f" en {p.coins:.8f} {base}" if p.in_position else "")
          + f" (budget €{config.LIVE_BUDGET_EUR:.2f})")


def keep_awake():
    """Windows: voorkom slaapstand zolang de bot draait (scherm mag wel uit)."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        print("Slaapstand staat uit zolang de bot draait (scherm mag wel uit).")
    except Exception:
        pass


def sell_reason(st, bid, now_ms):
    """Moet de huidige coin verkocht worden? Geeft (reden of None, uitleg)."""
    p = st["portfolio"]
    entry, peak = p.entry_price, st["peak"]
    held_min = (now_ms - st["opened_at"]) / 60_000
    net = bid * (1 - config.FEE_RATE) / entry - 1   # resultaat na verkoopkosten
    from_peak = bid / peak - 1
    info = (f"{st['market']} {net:+.2%} na kosten, {from_peak:+.1%} t.o.v. piek, "
            f"{held_min:.0f} min vast")

    if bid <= entry * (1 - config.POSITION_STOP_LOSS):
        return f"stop-loss: {net:+.1%} sinds aankoop", info
    if peak > entry and bid <= peak * (1 - config.TRAILING_STOP):
        return f"winst-stop: {from_peak:.1%} onder de piek", info
    if held_min >= config.HOLD_MINUTES and net <= 0:
        return f"{config.HOLD_MINUTES} min voorbij zonder winst ({net:+.2%})", info
    if held_min >= config.HOLD_MINUTES:
        return None, f"in winst, laat lopen tot {config.TRAILING_STOP:.0%} onder de piek · {info}"
    return None, info


def cmd_live(confirmed=False):
    import scanner

    if config.OPERATOR_ID is None:
        raise SystemExit("Zet eerst OPERATOR_ID in config.py (een getal naar keuze, bijv. 1001).")
    c = client_from_env()
    st = load_state()
    p = st["portfolio"]
    budget = config.LIVE_BUDGET_EUR
    floor = budget - config.LIVE_MAX_LOSS_EUR
    target = budget + config.LIVE_PROFIT_TARGET_EUR if config.LIVE_PROFIT_TARGET_EUR else None

    print("=" * 64)
    print("LET OP: ECHT GELD — scanner-strategie op alle euro-markten")
    print(f"Budget €{budget:.2f}, bot stopt helemaal onder €{floor:.2f}"
          + (f" of boven €{target:.2f}" if target else ""))
    print(f"Per coin: verkoop na {config.HOLD_MINUTES} min zonder winst, direct bij "
          f"-{config.POSITION_STOP_LOSS:.0%}, winnaars tot -{config.TRAILING_STOP:.0%} onder de piek")
    print(f"Max {config.LIVE_MAX_TRADES_PER_DAY} orders per dag")
    print(f"Boekhouding: €{p.eur:.2f}" + (f" + {p.coins:.8f} {st['market']}" if p.in_position else ""))
    print("=" * 64)
    if confirmed:
        print("Gestart met --ja (geen bevestigingsvraag).")
    elif input("Typ 'ja' om te starten: ").strip().lower() != "ja":
        print("Afgebroken.")
        return

    keep_awake()
    if config.DASHBOARD:
        import dashboard
        dashboard.start_background("live", open_browser=not confirmed or os.name == "nt")

    bid = ask = 0.0
    ranked, last_scan, skip_market = [], 0.0, None

    def status(reason, stopped=None):
        if not bid:
            return
        top = [{k: r[k] for k in ("market", "score", "ret_1h", "ret_4h", "ret_24h",
                                  "volume_eur", "spread", "uptrend")} for r in ranked[:6]]
        bot.write_status("live", p, bid, ask, [], reason, budget, floor, target, stopped,
                         market=st["market"], extra={
                             "strategy": "scanner", "peak": st["peak"],
                             "opened_at": st["opened_at"] if p.in_position else None,
                             "hold_minutes": config.HOLD_MINUTES,
                             "position_stop_loss": config.POSITION_STOP_LOSS,
                             "trailing_stop": config.TRAILING_STOP,
                             "trades_today": st["trades_today"],
                             "max_trades_per_day": config.LIVE_MAX_TRADES_PER_DAY,
                             "scan": top, "scanned_at": int(last_scan * 1000)})

    def sell(reason):
        nonlocal skip_market
        market = st["market"]
        base = market.split("-")[0]
        decimals = scanner.quantity_decimals(market)
        amount = floor_to(min(p.coins, c.balance(base)), decimals)
        if amount <= 0:
            p.coins, p.entry_price = 0.0, 0.0
            return
        res = c.order(market, "sell", amount=f"{amount:.{decimals}f}")
        coins, eur, fee = fill_summary(res, "sell", base)
        pnl = (eur / (coins * p.entry_price) - 1) * 100 if coins and p.entry_price else 0
        p.eur += eur
        p.coins = max(0.0, p.coins - coins)
        if p.coins * bid < 1:  # stofrestje: positie is dicht
            p.coins, p.entry_price = 0.0, 0.0
        st["trades_today"] += 1
        record(p, "sell", res, coins, eur, fee, reason, bid, market, pnl)
        skip_market = market if pnl <= 0 else None

    def buy(choice):
        nonlocal bid, ask
        market = choice["market"]
        base = market.split("-")[0]
        spend = floor_to(min(p.eur, config.MAX_PER_TRADE_EUR, c.balance("EUR")), 2)
        if spend < max(config.MIN_ORDER_EUR, choice["min_order_eur"]):
            return False
        res = c.order(market, "buy", amountQuote=f"{spend:.2f}")
        coins, eur, fee = fill_summary(res, "buy", base)
        if coins <= 0:
            return False
        p.eur = max(0.0, round(p.eur - eur, 8))  # geen -0,00 door afronding
        p.coins += coins
        p.entry_price = eur / coins
        st.update(market=market, peak=p.entry_price, opened_at=int(time.time() * 1000))
        st["trades_today"] += 1
        bid, ask = choice["bid"], choice["ask"]
        reason = (f"scanner: beste score ({choice['ret_4h']:+.1%} in 4 uur, "
                  f"{'trend omhoog' if choice['uptrend'] else 'geen duidelijke trend'})")
        record(p, "buy", res, coins, eur, fee, reason, bid, market)
        return True

    while True:
        try:
            if st["day"] != date.today().isoformat():
                st["day"], st["trades_today"] = date.today().isoformat(), 0
            now_ms = int(time.time() * 1000)
            stop, reason = None, ""

            if p.in_position:
                bid, ask = bot.get_book(st["market"])
                st["peak"] = max(st["peak"] or bid, bid)
                value = p.value(bid)
                if value <= floor:
                    stop = f"verliesgrens bereikt (waarde €{value:.2f})"
                elif target and value >= target:
                    stop = f"winstdoel bereikt (waarde €{value:.2f})"
                why, reason = sell_reason(st, bid, now_ms)
                if stop or why:
                    sell(stop or why)
                    reason = stop or why

            if not p.in_position and not stop:
                if p.eur <= floor:
                    stop = f"verliesgrens bereikt (waarde €{p.eur:.2f})"
                elif st["trades_today"] >= config.LIVE_MAX_TRADES_PER_DAY:
                    reason = f"daglimiet van {config.LIVE_MAX_TRADES_PER_DAY} orders bereikt, morgen weer"
                else:
                    ranked, last_scan = scanner.scan(), time.time()
                    choices = [r for r in ranked if r["market"] != skip_market] or ranked
                    if choices and buy(choices[0]):
                        reason = f"gekocht: {st['market']}"
                    else:
                        reason = "geen geschikte coin gevonden, volgende scan over een minuut"
            elif time.time() - last_scan > config.SCAN_MINUTES * 60:
                ranked, last_scan = scanner.scan(), time.time()  # alleen voor het dashboard

            save_state(st)
            status(reason, stop)
            print(f"[{bot.now()}] waarde €{p.value(bid):.2f} | {reason}")
            if stop:
                print(f"[{bot.now()}] {stop}. Alles staat weer in euro's. Bot stopt.")
                return
        except KeyboardInterrupt:
            raise
        except RuntimeError as e:  # fout van de beurs bij een order: niet doorgaan
            save_state(st)
            status(f"beursfout: {e}", f"beursfout: {e}")
            print(f"[{bot.now()}] Beursfout, bot stopt voor de veiligheid: {e}")
            return
        except Exception as e:  # netwerk hikt: later opnieuw
            print(f"[{bot.now()}] fout: {e}")
        time.sleep(config.POLL_SECONDS)


def record(p, side, res, coins, eur, fee, reason, price, market, pnl=0.0):
    p.fees_paid += fee
    p.trades += 1
    trade = {"side": side, "price": eur / coins if coins else 0, "amount": coins,
             "eur": eur, "fee": fee, "pnl_pct": pnl, "reason": f"{reason} [{res.get('status')}]"}
    bot.log_trade(trade, p, price, LIVE_TRADES_FILE, market)
    extra = f" ({pnl:+.2f}%)" if side == "sell" else ""
    print(f"[{bot.now()}] ECHT {side.upper()} {market}: {coins:.8g} voor €{eur:.2f}{extra} "
          f"(kosten €{fee:.4f}) — {reason}")
