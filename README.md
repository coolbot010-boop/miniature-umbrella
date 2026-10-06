# Bitvavo paper-trading-bot

Handelt met **nep-geld** op **echte live koersen** van Bitvavo. Geen account en geen API-key nodig, alleen Python 3.10+. Bij de eerste start installeert de bot zelf twee kleine pakketten (`truststore`, `certifi`) voor een betrouwbare beveiligde verbinding.

## Starten

```bash
python bot.py backtest        # test de strategie eerst op ~3 weken historie (15m-candles)
python bot.py backtest 5000   # langere periode
python bot.py run             # live paper trading, laat draaien; Ctrl+C om te stoppen
python bot.py status          # hoe staat de nep-portefeuille ervoor?
python bot.py reset           # opnieuw beginnen
```

Alle instellingen staan in `config.py`: markt, interval, startbudget (standaard €50), maximum per trade, kosten (0,25%), strategie, stop-loss en take-profit.

## Dashboard

Bij `python bot.py run` en `python bot.py live` opent automatisch een dashboard in je browser (http://localhost:8050). Daar zie je je portefeuillewaarde, winst/verlies, hoe ver je van je verliesgrens en winstdoel af zit, de koersgrafiek met koop- en verkoopmomenten, het huidige signaal en je laatste trades. Het ververst elke 5 seconden.

Los openen (bijv. als de bot in een ander venster draait): `python bot.py dashboard`. Uitzetten kan met `DASHBOARD = False` in `config.py`.

Het dashboard draait alleen op je eigen computer, gebruikt je API-key niet en kan geen orders plaatsen.

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

### Strategie bij echt handelen (scanner)

- Bij de start scant de bot **alle euro-markten** op Bitvavo en koopt **direct** de coin met de beste score (sterkste stijging van de laatste 4 uur ten opzichte van hoe wild hij beweegt, plus bonus bij een opwaartse trend).
- Coins met te weinig handel (< €250.000 per dag), een te groot verschil tussen koop- en verkoopprijs (> 0,3%), stablecoins en coins die vandaag al > 50% gestegen zijn, slaat hij over.
- **Na 15 minuten:** staat hij niet in winst, dan verkoopt hij en koopt hij direct de volgende beste coin.
- **In winst:** dan laat hij hem doorlopen tot de koers **20% onder de hoogste koers** sinds aankoop zakt (of de winst weg is).
- **Altijd:** verkopen als de koers **50% onder de aankoopprijs** komt.
- Alles is aan te passen in `config.py` (`HOLD_MINUTES`, `POSITION_STOP_LOSS`, `TRAILING_STOP`, `SCAN_*`).

Elke koop + verkoop kost samen ±0,5% aan kosten. Hoe vaker hij wisselt, hoe meer dat optelt.

Ingebouwde beveiligingen (in `config.py`):

| Instelling | Standaard | Wat het doet |
|---|---|---|
| `LIVE_BUDGET_EUR` | €50 | De bot gebruikt nooit meer van je euro's dan dit |
| `LIVE_MAX_LOSS_EUR` | €25 | Is de bot €25 kwijt (50%), dan verkoopt hij alles en stopt |
| `LIVE_PROFIT_TARGET_EUR` | geen | Winst heeft geen limiet (zet een bedrag om te stoppen bij winst) |
| `LIVE_MAX_TRADES_PER_DAY` | 20 | Na 20 orders koopt hij die dag niets meer; verkopen gaat altijd door |

- De bot verkoopt **alleen munten die hij zelf gekocht heeft**. Crypto die je al had, blijft staan.
- Had de vorige versie al bitcoin gekocht, dan neemt deze versie die over en past de nieuwe regels erop toe.
- Geeft de beurs een foutmelding op een order, dan stopt de bot direct in plaats van het opnieuw te proberen.
- De echte stand staat in `live_state.json`, elke echte order in `live_trades.csv`. Wil je opnieuw beginnen, verwijder dan `live_state.json` (de bot weet dan niet meer van eventuele munten die hij nog heeft).
- De bot draait alleen zolang je computer aan staat en het venster open is.

## Makkelijk starten op je laptop (Windows)

Dubbelklik op **`START-BOT.bat`**. De bot start meteen (zonder vraag) en het dashboard opent in je browser. Zolang het zwarte venster open is, draait de bot en gaat je laptop niet in slaapstand (je scherm mag wel uit). Venster sluiten = bot stoppen.

Let op: **klep dichtdoen zet een laptop meestal toch in slaap**. Wil je de klep dicht kunnen doen: Configuratiescherm → Energiebeheer → "Het gedrag van de aan/uit-knoppen bepalen" → bij klep sluiten "Niets doen" (op netstroom).

Automatisch starten als je laptop opstart: druk Win+R, typ `shell:startup`, Enter, en zet daar een snelkoppeling naar `START-BOT.bat`.

## 24/7 draaien op een server

Zo draait de bot dag en nacht zonder dat je laptop aan hoeft te staan.

1. Huur een kleine Linux-server (VPS) met **Ubuntu**, bijv. bij Hetzner, DigitalOcean of TransIP. De kleinste is genoeg.
2. **Stop de bot op je laptop** (Ctrl+C). Laat nooit twee bots tegelijk draaien op hetzelfde account.
3. Kopieer de hele map (inclusief `.env` en `live_state.json`) naar de server. In PowerShell, vanuit de tradebot-map:
   ```
   scp -r . root@JOUW-SERVER-IP:/root/tradebot
   ```
4. Log in en installeer:
   ```
   ssh root@JOUW-SERVER-IP
   bash /root/tradebot/install-server.sh
   ```
5. Dashboard bekijken vanaf je laptop: open PowerShell en laat dit venster open staan:
   ```
   ssh -L 8050:localhost:8050 root@JOUW-SERVER-IP
   ```
   Ga dan in je browser naar http://localhost:8050. Het dashboard is zo alleen voor jou bereikbaar.

Handig op de server:

| Wat | Commando |
|---|---|
| Meekijken wat de bot doet | `journalctl -u tradebot -f` |
| Stoppen | `systemctl stop tradebot` |
| Weer starten | `systemctl start tradebot` |

De bot start vanzelf opnieuw na een crash of een herstart van de server, maar **niet** als hij bewust gestopt is (verliesgrens bereikt of een foutmelding van de beurs op een order). Kijk dan eerst wat er aan de hand is.

> Geen financieel advies. Een strategie die in het verleden werkte, geeft geen garantie voor de toekomst. Zet er alleen geld op dat je kunt missen.
