"""Dashboard voor de tradebot: opent in je browser op http://localhost:8050

Start vanzelf mee met 'python bot.py run' en 'python bot.py live'.
Los openen kan met 'python bot.py dashboard'.
Het dashboard leest alleen bestanden en publieke koersen; het plaatst nooit orders
en gebruikt je API-key niet.
"""

import csv
import json
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import bot
import config

HERE = os.path.dirname(os.path.abspath(__file__))
TRADE_FILES = {"live": "live_trades.csv", "paper": config.TRADES_FILE}
_candle_cache = {}


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def read_history(mode, limit=1500):
    rows = []
    try:
        with open(f"history_{mode}.csv") as f:
            for line in f.readlines()[-limit:]:
                t, price, value = line.strip().split(",")
                rows.append([int(t), float(price), float(value)])
    except (OSError, ValueError):
        pass
    return rows


def read_trades(mode):
    try:
        with open(TRADE_FILES[mode], newline="") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def candles(market):
    """Laatste ~2 dagen candles met de gemiddelden, 60 sec gecachet per markt."""
    cache = _candle_cache.setdefault(market, {"t": 0, "data": []})
    if time.time() - cache["t"] > 60:
        try:
            raw = bot.get_candles(market, config.INTERVAL, limit=192 + config.SLOW_SMA)
            closes = [c[4] for c in raw]
            out = []
            for i, c in enumerate(raw):
                fast = sum(closes[i - config.FAST_SMA + 1:i + 1]) / config.FAST_SMA \
                    if i >= config.FAST_SMA - 1 else None
                slow = sum(closes[i - config.SLOW_SMA + 1:i + 1]) / config.SLOW_SMA \
                    if i >= config.SLOW_SMA - 1 else None
                out.append([c[0], c[4], fast, slow])
            cache.update(t=time.time(), data=out[config.SLOW_SMA:])
        except Exception:
            pass  # geen internet: oude data houden
    return cache["data"]


def data(mode):
    status = read_json(f"status_{mode}.json")
    trades = read_trades(mode)
    sells = [t for t in trades if t.get("kant") == "sell"]
    wins = sum(1 for t in sells if float(t.get("winst_%") or 0) > 0)
    stale = 3 * config.POLL_SECONDS * 1000 + 30_000
    running = bool(status and not status.get("stopped")
                   and time.time() * 1000 - status["updated"] < stale)
    market = (status or {}).get("market") or config.MARKET
    return {
        "mode": mode,
        "available": {m: os.path.exists(f"status_{m}.json") for m in ("live", "paper")},
        "status": status,
        "running": running,
        "history": read_history(mode),
        "candles": candles(market),
        "trades": trades[-50:],
        "wins": wins,
        "losses": len(sells) - wins,
        "market": market,
        "interval": config.INTERVAL,
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/api/data":
            mode = parse_qs(url.query).get("mode", ["live"])[0]
            body = json.dumps(data(mode if mode in TRADE_FILES else "live")).encode()
            ctype = "application/json"
        elif url.path == "/":
            with open(os.path.join(HERE, "dashboard.html"), "rb") as f:
                body = f.read()
            ctype = "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # geen serverlogs in de terminal
        pass


def serve(mode, open_browser=True):
    try:
        server = ThreadingHTTPServer(("127.0.0.1", config.DASHBOARD_PORT), Handler)
    except OSError:
        server = None  # draait al (bijv. in een ander venster)
    url = f"http://localhost:{config.DASHBOARD_PORT}/?mode={mode}"
    print(f"Dashboard: {url}")
    if open_browser:
        webbrowser.open(url)
    return server


def start_background(mode):
    server = serve(mode)
    if server:
        threading.Thread(target=server.serve_forever, daemon=True).start()


def cmd_dashboard():
    mode = "live" if os.path.exists("status_live.json") or not os.path.exists("status_paper.json") \
        else "paper"
    server = serve(mode)
    if not server:
        return
    print("Ctrl+C om het dashboard te sluiten.")
    server.serve_forever()
