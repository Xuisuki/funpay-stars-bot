"""
stats.py — счётчики статистики бота (персист в stats.json), потокобезопасно.

Проект: ProdX (https://prodx.pro)
Разработчик: Xuisuki — Telegram @Xuisuki, https://github.com/Xuisuki
"""
from __future__ import annotations

import copy
import json
import os
import threading
from datetime import datetime, timezone

import config

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats.json")
_lock = threading.RLock()


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _fresh():
    return {
        "orders": 0, "delivered": 0, "failed": 0, "refunded": 0,
        "stars_sold": 0, "turnover_rub": 0.0, "cost_usdt": 0.0,
        "fail_by_cat": {}, "by_day": {}, "started_at": None, "last_order": None,
    }


def _load():
    try:
        with open(_PATH, encoding="utf-8") as f:
            base = _fresh()
            base.update(json.load(f))
            return base
    except Exception:
        return _fresh()


_d = _load()


def _save():
    try:
        tmp = _PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_d, f, ensure_ascii=False)
        os.replace(tmp, _PATH)
    except Exception:
        pass


def _day():
    return _d["by_day"].setdefault(_today(), {"orders": 0, "delivered": 0, "stars": 0, "turnover": 0.0})


def mark_start():
    with _lock:
        _d["started_at"] = _now()
        _save()


def order():
    with _lock:
        _d["orders"] += 1
        _d["last_order"] = _now()
        _day()["orders"] += 1
        _save()


def delivered(stars: int, turnover_rub: float = 0.0, cost_usdt: float = 0.0):
    with _lock:
        _d["delivered"] += 1
        _d["stars_sold"] += int(stars or 0)
        _d["turnover_rub"] += float(turnover_rub or 0)
        _d["cost_usdt"] += float(cost_usdt or 0)
        day = _day()
        day["delivered"] += 1
        day["stars"] += int(stars or 0)
        day["turnover"] += float(turnover_rub or 0)
        _save()


def failed(cat: str):
    with _lock:
        _d["failed"] += 1
        _d["fail_by_cat"][cat] = _d["fail_by_cat"].get(cat, 0) + 1
        _save()


def refunded():
    with _lock:
        _d["refunded"] += 1
        _save()


def snapshot() -> dict:
    with _lock:
        return copy.deepcopy(_d)


def report(wallet: dict | None = None, usdt_per_50: float = 0.75, usdt_rub: float = 72.0) -> str:
    d = snapshot()
    today = d["by_day"].get(_today(), {})
    L = [f"Статистика — {config.brand()}", ""]
    if wallet and "error" not in wallet:
        usdt = float(wallet.get("usdt", 0) or 0)
        ton = float(wallet.get("ton", 0) or 0)
        left = int(usdt / usdt_per_50) if usdt_per_50 else 0
        L.append(f"Кошелёк: USDT {usdt:.2f} | TON {ton:.4f}")
        L.append(f"  хватит на ~{left} продаж по 50 звёзд")
    elif wallet:
        L.append(f"Кошелёк: ошибка чтения [{wallet.get('error')}]")
    L += ["",
          f"Заказы: всего {d['orders']} | выдано {d['delivered']} | сбои {d['failed']} | возвраты {d['refunded']}",
          f"Звёзд продано: {d['stars_sold']}"]
    cost_rub = d["cost_usdt"] * usdt_rub
    profit = d["turnover_rub"] - cost_rub
    L.append(f"Оборот ~{d['turnover_rub']:.0f} руб | себест. ~{cost_rub:.0f} ({d['cost_usdt']:.2f} USDT) | профит ~{profit:.0f}")
    if today:
        L += ["", f"Сегодня: заказов {today.get('orders', 0)}, выдано {today.get('delivered', 0)}, "
                  f"звёзд {today.get('stars', 0)}, оборот ~{today.get('turnover', 0):.0f} руб"]
    if d["fail_by_cat"]:
        L += ["", "Сбои: " + ", ".join(f"{k} {v}" for k, v in d["fail_by_cat"].items())]
    L += ["", f"Старт: {d.get('started_at') or '?'} | последний заказ: {d.get('last_order') or '—'}"]
    return "\n".join(L)
