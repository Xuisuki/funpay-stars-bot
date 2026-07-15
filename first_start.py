#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
first_start.py — мастер первичной настройки Funpay-Telegram-Stars.

Кастомный терминал-установщик (Rich): пошагово собирает .env — бренд, FunPay
(golden_key), режим DRY-RUN/боевой, self-hosted Fragment (seed остаётся ЛОКАЛЬНО),
Telegram-алерты. Показывает, где взять каждое значение, проверяет ввод, делает
бэкап старого .env и в конце может проверить авторизацию FunPay и кошелёк.

Запуск: python first_start.py   (или ./install.sh, который поставит зависимости)

Проект: ProdX (https://prodx.pro)
Разработчики: @Xuisuki + @mawlikow — github.com/Xuisuki, github.com/mawlikow
"""
from __future__ import annotations

import datetime as dt
import importlib
import os
import re
import shutil

import _wizard_ui as ui

ENV_PATH = ".env"
BACKUP_DIR = "backup_env"
TOTAL = 4

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

GROUPS = [
    ("бренд оператора (в баннере терминала)", ["BRAND_NAME", "BRAND_TAGLINE"]),
    ("FunPay", ["FUNPAY_AUTH_TOKEN", "FUNPAY_USER_AGENT", "STARS_SUBCATEGORY_ID", "DEACTIVATE_CATEGORY_ID"]),
    ("Fragment (self-hosted; seed остаётся ЛОКАЛЬНО)",
     ["FRAGMENT_SEED", "TON_API_KEY", "FRAGMENT_COOKIES", "FRAGMENT_WALLET_VERSION",
      "FRAGMENT_PAYMENT_METHOD", "FRAGMENT_SHOW_SENDER", "FRAGMENT_MIN_BALANCE"]),
    ("поведение выдачи", ["DRY_RUN", "STARS_MULTIPLY_BY_AMOUNT", "PREFLIGHT_BALANCE",
                          "AUTO_REFUND_ON_FAIL", "AUTO_DEACTIVATE", "LEDGER_DB"]),
    ("пейсер задержек", ["PACER_ENABLED", "REPLY_DELAY_MIN", "REPLY_DELAY_PER_ORDER",
                         "REPLY_DELAY_OFFSET", "REPLY_DELAY_MAX", "REPLY_JITTER"]),
    ("Telegram-алерты", ["TELEGRAM_BOT_TOKEN", "TELEGRAM_ADMIN_IDS"]),
    ("бонус за отзыв", ["REVIEW_BONUS_STARS", "REVIEW_SWEEP_INTERVAL"]),
    ("экономика/статистика", ["COST_USDT_PER_50", "USDT_RUB", "BALANCE_CHECK_INTERVAL",
                              "BALANCE_WARN_TON", "BALANCE_CRIT_TON"]),
]


# ---------------------------------------------------------------- валидаторы
def v_golden(s: str):
    if len(s.strip()) < 16:
        return "golden_key обычно ~32 символа. Скопируйте значение cookie целиком."
    return None


def v_int(s: str):
    return None if s.lstrip("-").isdigit() else "Нужно целое число."


def v_token(s: str):
    if not re.match(r"^\d{6,}:[A-Za-z0-9_-]{30,}$", s):
        return "Формат токена бота: 123456789:AA...(35+ символов)."
    return None


def v_ids(s: str):
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if parts and not all(p.lstrip("-").isdigit() for p in parts):
        return "id — числа через запятую (узнать: @userinfobot)."
    return None


# ---------------------------------------------------------------- .env I/O
def load_env(path):
    data = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def save_env(path, d):
    out = ["# Funpay-Telegram-Stars — конфигурация (сгенерировано мастером first_start.py)",
           "# by ProdX · prodx.pro · dev @Xuisuki + @mawlikow", ""]
    for gname, keys in GROUPS:
        out.append(f"# --- {gname} ---")
        for k in keys:
            v = d.get(k, DEFAULTS.get(k, ""))
            if any(c in v for c in (" ", ";", "#")) and not (v.startswith('"') and v.endswith('"')):
                v = f'"{v}"'
            out.append(f"{k}={v}")
        out.append("")
    open(path, "w", encoding="utf-8").write("\n".join(out))


def backup(path):
    if os.path.exists(path):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        dst = os.path.join(BACKUP_DIR, f".env.backup-{ts}")
        shutil.copy2(path, dst)
        ui.note(f"Старый .env сохранён -> {dst}")


# ---------------------------------------------------------------- flow
def main():
    ui.intro("Stars Bot", "FunPay -> Telegram Stars · автовыдача через self-hosted Fragment")
    e = load_env(ENV_PATH)
    if e:
        ui.note("Найден существующий .env — его значения предложены по умолчанию.")
    d = dict(DEFAULTS)
    d.update(e)

    # --- 1. бренд + FunPay ---
    ui.section(1, TOTAL, "Бренд и FunPay")
    d["BRAND_NAME"] = ui.ask_text(
        "BRAND_NAME", "Имя в баннере терминала. Пусто = имя вашего FunPay-аккаунта.",
        default=e.get("BRAND_NAME", ""), step="1/3")
    d["FUNPAY_AUTH_TOKEN"] = ui.ask_text(
        "FUNPAY_AUTH_TOKEN", "Ключ авторизации FunPay (golden_key) — по нему бот входит в ваш аккаунт.",
        where=["Войдите на funpay.com в браузере",
               "F12 -> Application (Storage) -> Cookies -> funpay.com",
               "Скопируйте значение cookie golden_key (~32 символа)"],
        default=e.get("FUNPAY_AUTH_TOKEN", ""), required=True, secret=True,
        validate=v_golden, step="2/3")
    d["STARS_SUBCATEGORY_ID"] = ui.ask_text(
        "STARS_SUBCATEGORY_ID", "id подкатегории FunPay, где лежат ваши лоты Stars.",
        where=["Откройте свою категорию лотов Stars на FunPay",
               "id — число в адресе страницы (например funpay.com/chips/2418/)"],
        default=e.get("STARS_SUBCATEGORY_ID", "2418"), validate=v_int, step="3/3")
    d["DEACTIVATE_CATEGORY_ID"] = d["STARS_SUBCATEGORY_ID"]

    # --- 2. режим ---
    ui.section(2, TOTAL, "Режим работы")
    dry = ui.ask_bool(
        "Тестовый режим (DRY-RUN)?",
        "DRY-RUN = бот отвечает и ведёт реестр, но НЕ отправляет звёзды и не тратит TON. "
        "Рекомендуется для обкатки. Боевой режим включите позже (DRY-RUN = нет).",
        default=e.get("DRY_RUN", "true").lower() in ("1", "true", "yes"), step="1/1")
    d["DRY_RUN"] = "true" if dry else "false"

    # --- 3. Fragment ---
    ui.section(3, TOTAL, "Fragment (выдача звёзд)")
    if dry:
        ui.note("Режим DRY-RUN — Fragment можно заполнить позже. Поля ниже необязательны сейчас.")
    else:
        ui.note("Боевой режим — нужны seed, TON_API_KEY и куки fragment.com.")
    d["FRAGMENT_SEED"] = ui.ask_text(
        "FRAGMENT_SEED", "Seed-фраза TON-кошелька-расходника. SELF-HOSTED: остаётся ЛОКАЛЬНО, наружу не уходит.",
        where=["Ваш TON-кошелёк (Tonkeeper и т.п.) -> настройки -> показать secret/recovery",
               "24 слова через пробел. Держите отдельный кошелёк только под выдачу"],
        default=e.get("FRAGMENT_SEED", ""), required=not dry, secret=True, step="1/5")
    d["TON_API_KEY"] = ui.ask_text(
        "TON_API_KEY", "Ключ TON API — через него бот шлёт транзакции.",
        where=["Зайдите на tonconsole.com", "Раздел API keys -> создайте ключ и скопируйте"],
        default=e.get("TON_API_KEY", ""), required=not dry, secret=True, step="2/5")
    d["FRAGMENT_COOKIES"] = ui.ask_text(
        "FRAGMENT_COOKIES", "Куки сессии fragment.com (живут часы — потом обновить).",
        where=["Войдите на fragment.com кошельком",
               "F12 -> Cookies -> fragment.com",
               "Соберите строкой: stel_ssid=...; stel_token=...; stel_ton_token=..."],
        default=e.get("FRAGMENT_COOKIES", ""), required=not dry, secret=True, step="3/5")
    d["FRAGMENT_WALLET_VERSION"] = ui.ask_choice(
        "FRAGMENT_WALLET_VERSION", "Версия кошелька TON (посмотрите в кошельке).",
        [("V5R1", "W5 — актуальная"), ("V4R2", "v4"), ("V4R1", "v4 старее"), ("V3R2", "v3")],
        default=e.get("FRAGMENT_WALLET_VERSION", "V5R1"), step="4/5")
    d["FRAGMENT_PAYMENT_METHOD"] = ui.ask_choice(
        "FRAGMENT_PAYMENT_METHOD", "Чем оплачивать звёзды на Fragment.",
        [("ton", "дешевле газ (рекомендуется)"), ("usdt_ton", "USDT в сети TON")],
        default=e.get("FRAGMENT_PAYMENT_METHOD", "ton"), step="5/5")

    # --- 4. Telegram-алерты ---
    ui.section(4, TOTAL, "Telegram-алерты оператору")
    d["TELEGRAM_BOT_TOKEN"] = ui.ask_text(
        "TELEGRAM_BOT_TOKEN", "Отдельный бот для уведомлений и команд /stats /pause (опционально).",
        where=["Откройте @BotFather -> /newbot", "Скопируйте токен вида 123456789:AA..."],
        default=e.get("TELEGRAM_BOT_TOKEN", ""), secret=True, validate=v_token, step="1/2")
    d["TELEGRAM_ADMIN_IDS"] = ui.ask_text(
        "TELEGRAM_ADMIN_IDS", "Ваши Telegram id (кому слать алерты), через запятую.",
        where=["Узнать свой id: напишите @userinfobot"],
        default=e.get("TELEGRAM_ADMIN_IDS", ""), validate=v_ids, step="2/2")

    # --- сводка ---
    ui.summary([
        ("Бренд", d["BRAND_NAME"] or "(имя FunPay)", False),
        ("FunPay golden_key", d["FUNPAY_AUTH_TOKEN"], True),
        ("Подкатегория Stars", d["STARS_SUBCATEGORY_ID"], False),
        ("Режим", "DRY-RUN (тест)" if dry else "БОЕВОЙ (реальная выдача)", False),
        ("Fragment seed", d["FRAGMENT_SEED"], True),
        ("TON API key", d["TON_API_KEY"], True),
        ("Кошелёк / оплата", f"{d['FRAGMENT_WALLET_VERSION']} / {d['FRAGMENT_PAYMENT_METHOD']}", False),
        ("Telegram bot", d["TELEGRAM_BOT_TOKEN"], True),
        ("Admin ids", d["TELEGRAM_ADMIN_IDS"] or "(нет)", False),
    ])
    if not ui.ask_bool("Сохранить в .env?",
                       "Записать значения в .env. Старый файл, если был, уйдёт в backup_env/.",
                       default=True):
        ui.bye("Отменено. Файл .env не тронут."); return

    backup(ENV_PATH)
    save_env(ENV_PATH, d)
    ui.check("Файл .env записан", True, ENV_PATH)

    # --- live-проверки ---
    if ui.ask_bool("Проверить авторизацию FunPay сейчас?",
                   "Войду в аккаунт по golden_key и покажу ник.", default=True):
        try:
            from FunPayAPI import Account
            acc = Account(d["FUNPAY_AUTH_TOKEN"]); acc.get()
            ui.check("FunPay авторизация", True, f"вошли как {getattr(acc, 'username', '?')}")
        except Exception as ex:
            ui.check("FunPay авторизация", False, str(ex))

    if not dry and d["FRAGMENT_SEED"] and ui.ask_bool(
            "Проверить чтение кошелька Fragment сейчас?", "Прочитаю баланс кошелька-расходника.",
            default=True):
        try:
            os.environ.update({k: str(v) for k, v in d.items()})
            import config as _c
            importlib.reload(_c)
            import fragment_stars as _fs
            importlib.reload(_fs)
            w = _fs.get_wallet_info()
            ui.check("Fragment кошелёк", "error" not in w, str(w))
        except Exception as ex:
            ui.check("Fragment кошелёк", False, str(ex))

    # --- финал ---
    ui.success(
        "Funpay-Telegram-Stars настроен.",
        "./run.sh   (Windows: run.ps1)",
        ["Бот слушает FunPay и выдаёт звёзды через Fragment.",
         "Сейчас режим: " + ("DRY-RUN — реальной выдачи нет." if dry else "БОЕВОЙ."),
         "Круглосуточно: см. deploy/ (systemd / launchd / Task Scheduler).",
         "Команды в Telegram-боте: /stats /review /pause."])


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        ui.bye("Прервано.")
