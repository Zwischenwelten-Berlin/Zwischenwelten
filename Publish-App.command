#!/bin/bash
# Doppelklick startet die Publish-App (Browser öffnet sich automatisch).
cd "$(dirname "$0")"
python3 scripts/publish_app.py
