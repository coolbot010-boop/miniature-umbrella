"""Paper-trading-bot voor Bitvavo.

Haalt echte koersen op via de publieke Bitvavo API (geen account nodig)
en handelt met nep-geld, inclusief tradekosten.

Gebruik:
    python bot.py run        # live paper trading (Ctrl+C om te stoppen)
    python bot.py backtest   # strategie testen op historische candles
    python bot.py backtest 5000   # ...met meer candles
    python bot.py status     # huidige stand van de nep-portefeuille
    python bot.py reset      # opnieuw beginnen met het startbudget

    python bot.py live-check # test je API-key (alleen lezen, geen orders)
    python bot.py live       # ECHT handelen met echt geld (zie live.py)
    python bot.py dashboard  # alleen het dashboard openen
"""

import csv
import json
import os
import sys
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import config

API = "https://api.bitvavo.com/v2"

# Gebruik de certificatenlijst van 'certifi' als die geïnstalleerd is
# (pip install certifi). Helpt als Windows een verouderde lijst heeft.
try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()
INTERVAL_MS = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000,
    "8h": 28_800_000, "12h": 43_200_000, "1d": 86_400_000,
}


# ---------------------------------------------------------------- API

def api_get(path, params=None):
    url = f"{API}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "paper-bot"})
    with urllib.request.urlopen(req, timeout=15, context=SSL_CONTEXT) as resp:
        return json.loads(resp.read())


def get_candles(market, interval, limit=100, end_ms=None):
    """Candles van oud naar nieuw: [timestamp, open, high, low, close, volume]."""
    params = {"interval": interval, "limit": limit}
    if end_ms:
        params["end"] = end_ms
    raw = api_get(f"{market}/candles", params)
    return [[int(c[0])] + [float(x) for x in c[1:]] for c in reversed(raw)]


def get_book(market):
    """Beste bied- en laatprijs. Kopen gaat tegen 'ask', verkopen tegen 'bid'."""
    data = api_get("ticker/book", {"market": market})
    return float(data["bid"]), float(data["ask"])


# ---------------------------------------------------------- Portfolio

@dataclass
class Portfolio:
    eur: float
    coins: float = 0.0
    entry_price: float = 0.0
    fees_paid: float = 0.0
    trades: int = 0

    @property
    def in_position(self):
        return self.coins > 0

    def value(self, price):
        return self.eur + self.coins * price

    def buy(self, price, fee_rate, max_eur):
        spend = min(self.eur, max_eur)
        if spend < config.MIN_ORDER_EUR:
            return None
        fee = spend * fee_rate
        amount = (spend - fee) / price
        self.eur -= spend
        self.coins += amount
        self.entry_price = price
        self.fees_paid += fee
        self.trades += 1
        return {"side": "buy", "price": price, "amount": amount, "eur": spend, "fee": fee}

    def sell(self, price, fee_rate):
        if not self.in_position:
            return None
        gross = self.coins * price
        fee = gross * fee_rate
        amount = self.coins
        pnl_pct = (price / self.entry_price - 1) * 100 if self.entry_price else 0
        self.eur += gross - fee
        self.coins = 0.0
        self.entry_price = 0.0
        self.fees_paid += fee
        self.trades += 1
        return {"side": "sell", "price": price, "amount": amount, "eur": gross - fee,
                "fee": fee, "pnl_pct": pnl_pct}


def load_portfolio():
    if os.path.exists(config.STATE_FILE):
        with open(config.STATE_FILE) as f:
            return Portfolio(**json.load(f))
    return Portfolio(eur=config.START_BUDGET_EUR)


def save_portfolio(p):
    with open(config.STATE_FILE, "w") as f:
        json.dump(asdict(p), f, indent=2)


def log_trade(trade, portfolio, price, path=None):
    path = path or config.TRADES_FILE
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["tijd", "markt", "kant", "prijs", "hoeveelheid", "eur",
                        "kosten", "winst_%", "reden", "portefeuille_eur"])
        w.writerow([
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            config.MARKET, trade["side"], f"{trade['price']:.2f}",
            f"{trade['amount']:.8f}", f"{trade['eur']:.2f}", f"{trade['fee']:.4f}",
            f"{trade.get('pnl_pct', 0):.2f}", trade.get("reason", ""),
            f"{portfolio.value(price):.2f}",
        ])


def write_status(mode, p, bid, ask, closes, reason, start, floor=None, target=None, stopped=None):
    """Schrijft de actuele stand weg voor het dashboard (status_<mode>.json + history_<mode>.csv)."""
    mid = (bid + ask) / 2
    now_ms = int(time.time() * 1000)
    fast = sma(closes, config.FAST_SMA) if len(closes) >= config.FAST_SMA else None
    slow = sma(closes, config.SLOW_SMA) if len(closes) >= config.SLOW_SMA else None
    status = {
        "mode": mode, "market": config.MARKET, "interval": config.INTERVAL,
        "updated": now_ms, "poll_seconds": config.POLL_SECONDS,
        "bid": bid, "ask": ask, "price": mid, "value": p.value(bid),
        "eur": p.eur, "coins": p.coins, "entry_price": p.entry_price,
        "fees_paid": p.fees_paid, "trades": p.trades,
        "start": start, "floor": floor, "target": target,
        "fast_sma": fast, "slow_sma": slow,
        "fast_n": config.FAST_SMA, "slow_n": config.SLOW_SMA,
        "stop_loss": config.STOP_LOSS, "take_profit": config.TAKE_PROFIT,
        "reason": reason, "stopped": stopped,
    }
    tmp = f"status_{mode}.json.tmp"
    with open(tmp, "w") as f:
        json.dump(status, f)
    os.replace(tmp, f"status_{mode}.json")
    with open(f"history_{mode}.csv", "a") as f:
        f.write(f"{now_ms},{mid:.2f},{p.value(bid):.4f}\n")


# ----------------------------------------------------------- Strategy

def sma(values, n):
    return sum(values[-n:]) / n


def decide(closes, portfolio, price):
    """Geeft ('buy'|'sell'|None, reden).

    closes: slotkoersen van *afgesloten* candles, oud -> nieuw.
    price:  koers waartegen we nu zouden handelen.
    """
    if len(closes) < config.SLOW_SMA + 1:
        return None, "te weinig data"

    if portfolio.in_position:
        change = price / portfolio.entry_price - 1
        if config.STOP_LOSS is not None and change <= -config.STOP_LOSS:
            return "sell", f"stop-loss ({change:+.2%})"
        if config.TAKE_PROFIT is not None and change >= config.TAKE_PROFIT:
            return "sell", f"take-profit ({change:+.2%})"

    fast_now, slow_now = sma(closes, config.FAST_SMA), sma(closes, config.SLOW_SMA)
    fast_prev = sma(closes[:-1], config.FAST_SMA)
    slow_prev = sma(closes[:-1], config.SLOW_SMA)

    if not portfolio.in_position and fast_prev <= slow_prev and fast_now > slow_now:
        return "buy", "SMA kruist omhoog"
    if portfolio.in_position and fast_prev >= slow_prev and fast_now < slow_now:
        return "sell", "SMA kruist omlaag"
    return None, f"wachten (snel {fast_now:.2f} / traag {slow_now:.2f})"


def execute(action, portfolio, bid, ask):
    if action == "buy":
        return portfolio.buy(ask, config.FEE_RATE, config.MAX_PER_TRADE_EUR)
    if action == "sell":
        return portfolio.sell(bid, config.FEE_RATE)
    return None


# ----------------------------------------------------------- Commands

def now():
    return datetime.now().strftime("%H:%M:%S")


def cmd_run():
    p = load_portfolio()
    step = INTERVAL_MS[config.INTERVAL]
    print(f"Paper trading {config.MARKET} ({config.INTERVAL}), €{p.eur:.2f} in kas, {p.coins:.8f} munten")
    print("Ctrl+C om te stoppen.\n")
    if config.DASHBOARD:
        import dashboard
        dashboard.start_background("paper")
    while True:
        try:
            candles = get_candles(config.MARKET, config.INTERVAL, limit=config.SLOW_SMA + 5)
            # Laatste candle is nog niet afgesloten: niet meenemen in signalen
            now_ms = int(time.time() * 1000)
            closes = [c[4] for c in candles if c[0] + step <= now_ms]
            bid, ask = get_book(config.MARKET)
            mid = (bid + ask) / 2

            action, reason = decide(closes, p, bid if p.in_position else ask)
            trade = execute(action, p, bid, ask)
            if trade:
                trade["reason"] = reason
                log_trade(trade, p, mid)
                save_portfolio(p)
                extra = f" ({trade['pnl_pct']:+.2f}%)" if trade["side"] == "sell" else ""
                print(f"[{now()}] {trade['side'].upper()} @ €{trade['price']:.2f}{extra} — {reason}")

            write_status("paper", p, bid, ask, closes, reason, config.START_BUDGET_EUR)
            print(f"[{now()}] koers €{mid:.2f} | waarde €{p.value(mid):.2f} | {reason}")
        except KeyboardInterrupt:
            raise
        except Exception as e:  # netwerk hikt: gewoon later opnieuw
            print(f"[{now()}] fout: {e}")
        time.sleep(config.POLL_SECONDS)


def simulate(candles, slippage=0.0005):
    """Draait de strategie over historische candles. Geeft (portfolio, laatste prijs)."""
    p = Portfolio(eur=config.START_BUDGET_EUR)
    closes = []
    for c in candles:
        closes.append(c[4])
        price = c[4]
        bid, ask = price * (1 - slippage), price * (1 + slippage)
        action, _ = decide(closes, p, bid if p.in_position else ask)
        execute(action, p, bid, ask)
    return p, closes[-1]


def fetch_history(market, interval, total):
    candles, end = [], None
    while len(candles) < total:
        batch = get_candles(market, interval, limit=min(1440, total - len(candles)), end_ms=end)
        if not batch:
            break
        candles = batch + candles
        end = batch[0][0] - 1
    return candles


def cmd_backtest(n_candles=2000):
    print(f"Historische candles ophalen: {config.MARKET} {config.INTERVAL} x {n_candles} ...")
    candles = fetch_history(config.MARKET, config.INTERVAL, n_candles)
    report(candles)


def report(candles):
    p, last = simulate(candles)
    start = config.START_BUDGET_EUR
    final = p.value(last * (1 - config.FEE_RATE))
    hold = start * (1 - config.FEE_RATE) ** 2 * last / candles[0][4]
    first = datetime.fromtimestamp(candles[0][0] / 1000).strftime("%Y-%m-%d")
    lastd = datetime.fromtimestamp(candles[-1][0] / 1000).strftime("%Y-%m-%d")
    print(f"\nPeriode:        {first} t/m {lastd} ({len(candles)} candles)")
    print(f"Startkapitaal:  €{start:.2f}")
    print(f"Eindwaarde:     €{final:.2f} ({(final / start - 1) * 100:+.2f}%)")
    print(f"Aantal trades:  {p.trades}")
    print(f"Betaalde kosten: €{p.fees_paid:.2f}")
    print(f"Ter vergelijking, gewoon kopen en vasthouden: €{hold:.2f} "
          f"({(hold / start - 1) * 100:+.2f}%)")
    return final


def cmd_status():
    p = load_portfolio()
    bid, ask = get_book(config.MARKET)
    mid = (bid + ask) / 2
    v = p.value(bid)
    start = config.START_BUDGET_EUR
    print(f"Markt:        {config.MARKET} @ €{mid:.2f}")
    print(f"Kas:          €{p.eur:.2f}")
    print(f"Munten:       {p.coins:.8f}" + (f" (gekocht @ €{p.entry_price:.2f})" if p.in_position else ""))
    print(f"Waarde:       €{v:.2f} ({(v / start - 1) * 100:+.2f}% t.o.v. €{start:.2f})")
    print(f"Trades:       {p.trades}, kosten betaald: €{p.fees_paid:.2f}")


def cmd_reset():
    for f in (config.STATE_FILE, config.TRADES_FILE, "status_paper.json", "history_paper.csv"):
        if os.path.exists(f):
            os.remove(f)
    print(f"Gereset. Nieuw startbudget: €{config.START_BUDGET_EUR:.2f}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    import live
    import dashboard
    commands = {"dashboard": dashboard.cmd_dashboard, "run": cmd_run, "backtest": cmd_backtest, "status": cmd_status, "reset": cmd_reset,
                "live-check": live.cmd_check, "live": live.cmd_live}
    if cmd not in commands:
        print(__doc__)
        sys.exit(1)
    try:
        commands[cmd](*[int(a) for a in sys.argv[2:3]])
    except KeyboardInterrupt:
        print("\nGestopt. Stand is opgeslagen.")
    except urllib.error.URLError as e:
        if isinstance(e.reason, ssl.SSLCertVerificationError):
            print(SSL_HELP.format(fout=e.reason.verify_message, tijd=datetime.now().strftime("%d-%m-%Y %H:%M")))
        else:
            print(f"Geen verbinding met Bitvavo: {e.reason}. Check je internet en probeer opnieuw.")
        sys.exit(1)


SSL_HELP = """
Je computer vertrouwt de beveiligde verbinding met Bitvavo niet ({fout}).
Dit ligt niet aan de bot of je API-key. Probeer, in deze volgorde:

1. Klopt de datum en tijd van je computer? Volgens je pc is het nu: {tijd}
   Zo niet: Instellingen > Tijd en taal > 'Tijd automatisch instellen' aan,
   en klik op 'Nu synchroniseren'.
2. Installeer een actuele certificatenlijst:   pip install certifi
   en probeer het daarna opnieuw.
3. Heb je een virusscanner zoals Avast, AVG, Kaspersky of ESET? Zet daarin
   'HTTPS-scannen' / 'webschild' uit, of voeg Python toe als uitzondering.
"""


if __name__ == "__main__":
    main()
