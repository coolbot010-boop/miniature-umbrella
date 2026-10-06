# Bitvavo paper-trading-bot

Handelt met **nep-geld** op **echte live koersen** van Bitvavo. Geen account, geen API-key en geen extra pakketten nodig, alleen Python 3.9+.

## Starten

```bash
python bot.py backtest        # test de strategie eerst op ~3 weken historie (15m-candles)
python bot.py backtest 5000   # langere periode
python bot.py run             # live paper trading, laat draaien; Ctrl+C om te stoppen
python bot.py status          # hoe staat de nep-portefeuille ervoor?
python bot.py reset           # opnieuw beginnen
```

Alle instellingen staan in `config.py`: markt, interval, startbudget (standaard €50), maximum per trade, kosten (0,25%), strategie, stop-loss en take-profit.

## Hoe het werkt

- **Strategie:** moving-average crossover. Kopen als het snelle gemiddelde (9 candles) het trage (21) van onder naar boven kruist, verkopen bij de omgekeerde kruising. Daarnaast een stop-loss (−3%) en take-profit (+6%).
- **Realistische vulling:** kopen gebeurt tegen de laatprijs (ask), verkopen tegen de biedprijs (bid). Bij het kopen en verkopen gaat er 0,25% kosten af.
- **Alleen afgesloten candles** tellen mee voor signalen, zodat een half gevormde candle geen valse signalen geeft.
- **Budgetlimiet:** de bot zet nooit meer in dan `START_BUDGET_EUR`, en per trade nooit meer dan `MAX_PER_TRADE_EUR`. Orders onder €5 slaat hij over (het Bitvavo-minimum).
- De stand wordt bewaard in `paper_state.json`, elke trade in `trades.csv` (te openen in Excel).

De backtest vergelijkt het resultaat ook met **gewoon kopen en vasthouden**. Verslaat de bot dat na kosten niet, dan heeft de strategie geen zin.

## Daarna (pas als paper trading een tijd goed gaat)

1. Maak een Bitvavo-account en verifieer het.
2. Maak een API-key aan met **alleen "Bekijken" en "Handelen", nooit "Opnemen"**.
3. Kopieer `.env.example` naar `.env` en vul de key in. `.env` staat in `.gitignore` en komt dus nooit in git.
4. Begin klein (€20–50). Echt handelen zit er nog niet in. Dat bouwen we pas als je zover bent.

> Geen financieel advies. Een strategie die in het verleden werkte, geeft geen garantie voor de toekomst.
