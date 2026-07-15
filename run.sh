#!/usr/bin/env bash
# Funpay-Telegram-Stars — запуск бота (слушает FunPay, выдаёт звёзды).
set -euo pipefail
cd "$(dirname "$0")"
VPY=".venv/bin/python"; [ -f "$VPY" ] || VPY=".venv/Scripts/python"
[ -f "$VPY" ] || { echo "Сначала запустите ./install.sh"; exit 1; }
exec "$VPY" bot_fragment.py "$@"
