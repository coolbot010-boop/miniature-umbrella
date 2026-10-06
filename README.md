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

## Echt handelen

1. Maak een Bitvavo-account en verifieer het. Zet er een klein bedrag op (bijv. €20–50).
2. Maak een API-key aan (Instellingen → API) met **alleen "Bekijken" en "Handelen", nooit "Opnemen"**. Zet bij voorkeur een IP-whitelist aan.
3. Kopieer `.env.example` naar `.env` en vul key + secret in. `.env` staat in `.gitignore` en komt dus nooit in git.
4. `OPERATOR_ID` in `config.py` staat al op `1001` (Bitvavo verplicht dit bij elke order).
5. Test de key zonder iets te kopen: `python bot.py live-check`
6. Start: `python bot.py live` en typ `ja`.

Ingebouwde beveiligingen (in `config.py`):

| Instelling | Standaard | Wat het doet |
|---|---|---|
| `LIVE_BUDGET_EUR` | €50 | De bot gebruikt nooit meer van je euro's dan dit |
| `LIVE_MAX_LOSS_EUR` | €15 | Is de bot €15 kwijt, dan stopt hij helemaal |
| `LIVE_MAX_TRADES_PER_DAY` | 10 | Voorkomt dat een fout je saldo opvreet met kosten |

- De bot verkoopt **alleen munten die hij zelf gekocht heeft**. Crypto die je al had, blijft staan.
- Geeft de beurs een foutmelding op een order, dan stopt de bot direct in plaats van het opnieuw te proberen.
- De echte stand staat in `live_state.json`, elke echte order in `live_trades.csv`. Wil je opnieuw beginnen, verwijder dan `live_state.json` (de bot weet dan niet meer van eventuele munten die hij nog heeft).
- De bot draait alleen zolang je computer aan staat en het venster open is.

> Geen financieel advies. Een strategie die in het verleden werkte, geeft geen garantie voor de toekomst. Zet er alleen geld op dat je kunt missen.
