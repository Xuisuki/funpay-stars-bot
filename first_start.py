"""
first_start.py — мастер первичной настройки Funpay-Telegram-Stars.

Собирает .env: FunPay, self-hosted Fragment (seed локально), бренд, Telegram-алерты.
Опционально проверяет авторизацию FunPay и чтение кошелька Fragment.

Проект: ProdX (https://prodx.pro)
Разработчик: Xuisuki — Telegram @Xuisuki, https://github.com/Xuisuki
"""
from __future__ import annotations

import datetime as dt
import os
import shutil

try:
    from colorama import init as _ci, Fore, Style
    _ci(autoreset=True)
except Exception:
    class _D:
        RESET_ALL = ""

    class _F(_D):
        RED = GREEN = YELLOW = CYAN = MAGENTA = ""

    class _S(_D):
        BRIGHT = ""
    Fore, Style = _F(), _S()

ENV_PATH = ".env"
BACKUP_DIR = "backup_env"

# Полный набор ключей с дефолтами (то, что не спрашиваем — пишется как есть).
DEFAULTS = {
    "BRAND_NAME": "", "BRAND_TAGLINE": "",
    "FUNPAY_AUTH_TOKEN": "", "FUNPAY_USER_AGENT": "",
    "STARS_SUBCATEGORY_ID": "2418", "DEACTIVATE_CATEGORY_ID": "2418",
    "FRAGMENT_SEED": "", "TON_API_KEY": "", "FRAGMENT_COOKIES": "",
    "FRAGMENT_WALLET_VERSION": "V5R1", "FRAGMENT_PAYMENT_METHOD": "ton",
    "FRAGMENT_SHOW_SENDER": "false", "FRAGMENT_MIN_BALANCE": "1.0",
    "DRY_RUN": "true", "STARS_MULTIPLY_BY_AMOUNT": "true", "PREFLIGHT_BALANCE": "true",
    "AUTO_REFUND_ON_FAIL": "false", "AUTO_DEACTIVATE": "true", "LEDGER_DB": "orders.db",
    "PACER_ENABLED": "true", "REPLY_DELAY_MIN": "15", "REPLY_DELAY_PER_ORDER": "18",
    "REPLY_DELAY_OFFSET": "30", "REPLY_DELAY_MAX": "600", "REPLY_JITTER": "0.15",
    "TELEGRAM_BOT_TOKEN": "", "TELEGRAM_ADMIN_IDS": "",
    "REVIEW_BONUS_STARS": "1", "REVIEW_SWEEP_INTERVAL": "1200",
    "COST_USDT_PER_50": "0.75", "USDT_RUB": "72.0",
    "BALANCE_CHECK_INTERVAL": "600", "BALANCE_WARN_TON": "0.5", "BALANCE_CRIT_TON": "0.1",
}


def info(m): print(Fore.CYAN + m)
def ok(m): print(Fore.GREEN + m)
def warn(m): print(Fore.YELLOW + m)
def err(m): print(Fore.RED + m)


def ask(label, default="", allow_empty=True):
    d = f" [{default}]" if default else ""
    v = input(f"{label}{d}: ").strip()
    if not v and default:
        return default
    if not v and not allow_empty:
        while not v:
            v = input(f"{label} (обязательно): ").strip()
    return v


def ask_bool(label, default: bool):
    d = "Y/n" if default else "y/N"
    a = input(f"{label} ({d}): ").strip().lower()
    if not a:
        return default
    return a in ("y", "yes", "д", "да")


def load_env(path):
    data = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip().strip('"')
    return data


def save_env(path, data):
    lines = []
    for k in DEFAULTS:
        v = data.get(k, DEFAULTS[k])
        if any(c in v for c in (" ", ";", "#")) and not (v.startswith('"') and v.endswith('"')):
            v = f'"{v}"'
        lines.append(f"{k}={v}")
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    ok(f"Сохранено в {path}")


def backup(path):
    if os.path.exists(path):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        dst = os.path.join(BACKUP_DIR, f".env.backup-{ts}")
        shutil.copy2(path, dst)
        warn(f"Бэкап {path} -> {dst}")


def main():
    print(Style.BRIGHT + Fore.MAGENTA + "—" * 56)
    print(Style.BRIGHT + Fore.CYAN + "Настройка Funpay-Telegram-Stars   by ProdX (prodx.pro)")
    print(Style.BRIGHT + Fore.MAGENTA + "—" * 56)
    e = load_env(ENV_PATH)
    if e:
        warn("Найден .env — текущие значения предложены по умолчанию.\n")
    d = dict(DEFAULTS)
    d.update(e)

    info("1) Бренд и FunPay")
    d["BRAND_NAME"] = ask("BRAND_NAME (имя в баннере; пусто = имя FunPay)", e.get("BRAND_NAME", ""))
    d["FUNPAY_AUTH_TOKEN"] = ask("FUNPAY_AUTH_TOKEN (golden_key, 32 символа)",
                                 e.get("FUNPAY_AUTH_TOKEN", ""), allow_empty=False)
    d["STARS_SUBCATEGORY_ID"] = ask("STARS_SUBCATEGORY_ID (подкатегария Stars)",
                                    e.get("STARS_SUBCATEGORY_ID", "2418"))
    d["DEACTIVATE_CATEGORY_ID"] = d["STARS_SUBCATEGORY_ID"]

    print()
    info("2) Режим")
    dry = ask_bool("DRY_RUN (тест без реальной отправки)?",
                   e.get("DRY_RUN", "true").lower() in ("1", "true", "yes"))
    d["DRY_RUN"] = "true" if dry else "false"

    print()
    info("3) Fragment (self-hosted; seed остаётся ЛОКАЛЬНО)")
    if not dry:
        warn("Боевой режим — нужны seed/TON_API_KEY/куки.")
    d["FRAGMENT_SEED"] = ask("FRAGMENT_SEED (seed-фраза кошелька)", e.get("FRAGMENT_SEED", ""))
    d["TON_API_KEY"] = ask("TON_API_KEY (tonconsole.com)", e.get("TON_API_KEY", ""))
    d["FRAGMENT_COOKIES"] = ask("FRAGMENT_COOKIES (stel_*; строкой k=v; k=v)", e.get("FRAGMENT_COOKIES", ""))
    d["FRAGMENT_WALLET_VERSION"] = ask("FRAGMENT_WALLET_VERSION", e.get("FRAGMENT_WALLET_VERSION", "V5R1"))
    d["FRAGMENT_PAYMENT_METHOD"] = ask("FRAGMENT_PAYMENT_METHOD (ton/usdt_ton)",
                                       e.get("FRAGMENT_PAYMENT_METHOD", "ton"))

    print()
    info("4) Telegram-алерты (опционально, но рекомендуется)")
    d["TELEGRAM_BOT_TOKEN"] = ask("TELEGRAM_BOT_TOKEN (@BotFather)", e.get("TELEGRAM_BOT_TOKEN", ""))
    d["TELEGRAM_ADMIN_IDS"] = ask("TELEGRAM_ADMIN_IDS (ваши id через запятую)", e.get("TELEGRAM_ADMIN_IDS", ""))

    print()
    info("Проверьте:")
    print(f"  BRAND_NAME              = {d['BRAND_NAME'] or '(имя FunPay)'}")
    print(f"  FUNPAY_AUTH_TOKEN       = {_mask(d['FUNPAY_AUTH_TOKEN'])}")
    print(f"  STARS_SUBCATEGORY_ID    = {d['STARS_SUBCATEGORY_ID']}")
    print(f"  DRY_RUN                 = {d['DRY_RUN']}")
    print(f"  FRAGMENT_SEED           = {_mask(d['FRAGMENT_SEED'], 2, 2)}")
    print(f"  TON_API_KEY             = {_mask(d['TON_API_KEY'])}")
    print(f"  FRAGMENT_WALLET_VERSION = {d['FRAGMENT_WALLET_VERSION']}")
    print(f"  FRAGMENT_PAYMENT_METHOD = {d['FRAGMENT_PAYMENT_METHOD']}")
    print(f"  TELEGRAM_ADMIN_IDS      = {d['TELEGRAM_ADMIN_IDS'] or '(нет)'}")
    print()
    if not ask_bool("Сохранить в .env?", True):
        err("Отмена."); return

    backup(ENV_PATH)
    save_env(ENV_PATH, d)

    print()
    if ask_bool("Проверить авторизацию FunPay сейчас?", True):
        try:
            from FunPayAPI import Account
            acc = Account(d["FUNPAY_AUTH_TOKEN"]); acc.get()
            ok(f"FunPay: авторизован как {getattr(acc, 'username', '?')}")
        except Exception as ex:
            err(f"FunPay: {ex}")

    if not dry and ask_bool("Проверить чтение кошелька Fragment сейчас?", True):
        try:
            os.environ.update({k: v for k, v in d.items()})
            import importlib
            import config as _c
            importlib.reload(_c)
            import fragment_stars as _fs
            importlib.reload(_fs)
            w = _fs.get_wallet_info()
            (ok if "error" not in w else err)(f"Fragment: {w}")
        except Exception as ex:
            err(f"Fragment: {ex}")

    print()
    ok("Готово. Запуск: python bot_fragment.py")


def _mask(s, head=3, tail=3):
    if not s:
        return ""
    if len(s) <= head + tail:
        return "*" * len(s)
    return s[:head] + "*" * (len(s) - head - tail) + s[-tail:]


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        warn("Прервано.")
