#!/usr/bin/env bash
# Funpay-Telegram-Stars — установщик для Linux / macOS.
# Проверяет Python, создаёт .venv, ставит зависимости и запускает мастер настройки.
# by ProdX (prodx.pro) · dev @Xuisuki + @mawlikow
set -euo pipefail
cd "$(dirname "$0")"

c()   { printf '\033[%sm' "$1"; }
CY=$(c '38;5;44'); GN=$(c '38;5;42'); RD=$(c '38;5;203'); DIM=$(c '2'); R=$(c '0')

echo
echo "  ${CY}==================================================${R}"
echo "  ${CY}  Funpay-Telegram-Stars${R}  ${DIM}— установщик${R}"
echo "  ${DIM}  by ProdX · prodx.pro · dev @Xuisuki + @mawlikow${R}"
echo "  ${CY}==================================================${R}"
echo

# 1) Python
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then
    if "$c" -c 'import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)' 2>/dev/null; then PY="$c"; break; fi
  fi
done
if [ -z "$PY" ]; then
  echo "  ${RD}[1/4] Не найден Python 3.9+${R}"
  echo "        Установите Python: https://www.python.org/downloads/  (Linux: apt install python3 python3-venv)"
  exit 1
fi
echo "  ${GN}[1/4]${R} Python: $("$PY" --version 2>&1)"

# 2) venv
if [ ! -d .venv ]; then
  echo "  ${CY}[2/4]${R} Создаю виртуальное окружение .venv ..."
  "$PY" -m venv .venv
else
  echo "  ${GN}[2/4]${R} .venv уже есть"
fi
VPY=".venv/bin/python"; [ -f "$VPY" ] || VPY=".venv/Scripts/python"

# 3) зависимости
echo "  ${CY}[3/4]${R} Ставлю зависимости (может занять пару минут — tonutils/крипта) ..."
"$VPY" -m pip install --quiet --upgrade pip
"$VPY" -m pip install --quiet -r requirements.txt
echo "  ${GN}[3/4]${R} Зависимости готовы"

# 4) мастер настройки
echo "  ${CY}[4/4]${R} Запускаю мастер настройки ..."
echo
"$VPY" first_start.py

echo
echo "  ${GN}Установка завершена.${R} Запуск бота: ${CY}./run.sh${R}"
