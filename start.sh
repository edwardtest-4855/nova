#!/bin/sh
cd "$(dirname "$0")"
set -e
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
if [ -f .env ]; then set -a; . ./.env; set +a; fi
python server.py
