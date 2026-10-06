#!/usr/bin/env bash
# Installeert de tradebot als achtergronddienst op een Ubuntu/Debian-server.
# Gebruik (op de server, in de tradebot-map):   bash install-server.sh
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if [ ! -f .env ]; then
  echo "Geen .env gevonden in $DIR. Kopieer eerst je tradebot-map inclusief .env naar de server."
  exit 1
fi

echo "== Python installeren =="
apt-get update -qq
apt-get install -y -qq python3 python3-venv >/dev/null

echo "== Eigen Python-omgeving maken =="
python3 -m venv "$DIR/venv"
"$DIR/venv/bin/pip" install --quiet --upgrade pip
"$DIR/venv/bin/pip" install --quiet -r "$DIR/requirements.txt"

echo "== Tijd automatisch gelijk houden =="
timedatectl set-ntp true || true

echo "== Dienst aanmaken =="
cat > /etc/systemd/system/tradebot.service <<UNIT
[Unit]
Description=Bitvavo tradebot
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$DIR
ExecStart=$DIR/venv/bin/python -u $DIR/bot.py live --ja
# Alleen herstarten na een crash, niet als de bot bewust stopt
# (verliesgrens bereikt of foutmelding van de beurs op een order).
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now tradebot

echo
echo "Klaar! De bot draait nu 24/7 en start vanzelf na een herstart van de server."
echo "  Meekijken:   journalctl -u tradebot -f      (Ctrl+C = stoppen met kijken)"
echo "  Stoppen:     systemctl stop tradebot"
echo "  Starten:     systemctl start tradebot"
