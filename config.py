"""Instellingen voor de paper-trading-bot. Pas gerust aan."""

# Welke markt en candle-interval (1m, 5m, 15m, 30m, 1h, 4h, 1d)
MARKET = "BTC-EUR"
INTERVAL = "15m"

# Startkapitaal in (nep-)euro's. Dit is ook de harde limiet:
# de bot zet nooit meer in dan dit bedrag.
START_BUDGET_EUR = 50.0

# Maximaal bedrag per aankoop (kan nooit meer zijn dan wat er nog in kas is)
MAX_PER_TRADE_EUR = 50.0

# Bitvavo minimumorder is ~€5; kleinere orders slaat de bot over
MIN_ORDER_EUR = 5.0

# Kosten per trade. Bitvavo rekent ~0,25% (taker) bij lage volumes.
FEE_RATE = 0.0025

# Strategie: moving-average crossover
FAST_SMA = 9      # aantal candles voor het snelle gemiddelde
SLOW_SMA = 21     # aantal candles voor het trage gemiddelde

# Risicobeheer (als fractie: 0.03 = 3%). Zet op None om uit te schakelen.
STOP_LOSS = 0.03
TAKE_PROFIT = 0.06

# Hoe vaak de bot kijkt (seconden)
POLL_SECONDS = 60

# Dashboard: opent automatisch in je browser bij 'run' en 'live'
DASHBOARD = True
DASHBOARD_PORT = 8050

# Bestanden
STATE_FILE = "paper_state.json"
TRADES_FILE = "trades.csv"

# ------------------------------------------------- Echt handelen (bot.py live)
# Harde limiet: de bot gebruikt nooit meer dan dit bedrag van je echte euro's.
LIVE_BUDGET_EUR = 50.0

# Verliesgrens: is de bot dit bedrag kwijt, dan verkoopt hij alles en stopt.
LIVE_MAX_LOSS_EUR = 25.0

# Winstdoel: heeft de bot dit bedrag verdiend, dan verkoopt hij alles en stopt.
LIVE_PROFIT_TARGET_EUR = 50.0

# Beschermt tegen een bot die door een fout blijft kopen/verkopen.
LIVE_MAX_TRADES_PER_DAY = 10

# Bitvavo verplicht een operatorId bij elke order: een vast getal naar keuze
# dat deze bot identificeert, bijvoorbeeld 1001.
OPERATOR_ID = 1001
