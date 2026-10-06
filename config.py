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

# Winstdoel voor de hele portefeuille. None = nooit stoppen bij winst.
LIVE_PROFIT_TARGET_EUR = None

# Maximaal aantal orders per dag (kopen + verkopen samen). Na deze grens koopt
# hij die dag niets meer; verkopen bij stop-loss of winst-stop gaat altijd door.
# Elke koop+verkoop kost ~0,5% kosten, dus hoger = meer kosten.
LIVE_MAX_TRADES_PER_DAY = 20

# ------------------------------------------------- Scanner-strategie (live)
# Na zoveel minuten verkoopt hij als hij niet in winst staat.
HOLD_MINUTES = 15

# Altijd direct verkopen als de koers zoveel onder de aankoopprijs komt (0.50 = 50%).
POSITION_STOP_LOSS = 0.50

# Staat hij in winst, dan laat hij hem doorlopen tot de koers zoveel onder de
# hoogste koers sinds aankoop zakt (0.20 = 20%).
TRAILING_STOP = 0.20

# Scanner-filters
SCAN_MIN_VOLUME_EUR = 250_000   # minimale handel per dag in euro's
SCAN_MAX_SPREAD = 0.003         # max verschil koop-/verkoopprijs (0,3%)
SCAN_TOP_N = 30                 # zoveel meest verhandelde coins beoordelen
SCAN_MAX_PUMP = 0.50            # coins die vandaag al >50% stegen overslaan
SCAN_MINUTES = 15               # zo vaak opnieuw scannen (voor het dashboard)

# Bitvavo verplicht een operatorId bij elke order: een vast getal naar keuze
# dat deze bot identificeert, bijvoorbeeld 1001.
OPERATOR_ID = 1001
