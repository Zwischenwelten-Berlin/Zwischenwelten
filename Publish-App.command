#!/bin/bash
# Doppelklick startet die Publish-App (Browser öffnet sich automatisch).
# Läuft noch eine alte Instanz (z. B. nach geschlossenem Fenster), wird sie
# vorher beendet, damit Port 8765 frei ist.
cd "$(dirname "$0")"
OLD=$(lsof -ti :8765)
if [ -n "$OLD" ]; then
  echo "Beende alte Publish-App (PID $OLD) …"
  kill $OLD
  sleep 1
fi
python3 scripts/publish_app.py
