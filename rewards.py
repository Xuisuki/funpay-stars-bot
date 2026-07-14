"""
rewards.py — бонус за отзыв: +N звёзд к следующему заказу. Персист в rewards.json.

Логика:
- record_delivery(oid, buyer): запомнили выданный заказ (для отслеживания отзыва).
- когда по заказу появился review -> add_rewarded(oid) + grant(buyer, N) (начислили «в долг»).
- при новом заказе: peek(buyer) -> сколько бонуса ждёт; consume(buyer) после успешной выдачи.

Проект: ProdX (https://prodx.pro)
Разработчик: Xuisuki — Telegram @Xuisuki, https://github.com/Xuisuki
"""
from __future__ import annotations

import copy
import json
import os
import threading

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rewards.json")
_lock = threading.RLock()


def _fresh():
    return {"delivered": {}, "rewarded": [], "pending": {}}


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


def record_delivery(oid, buyer_id) -> None:
    if buyer_id is None:
        return
    with _lock:
        _d["delivered"][str(oid)] = buyer_id
        _save()


def buyer_of(oid):
    return _d["delivered"].get(str(oid))


def already_rewarded(oid) -> bool:
    return str(oid) in _d["rewarded"]


def add_rewarded(oid) -> None:
    with _lock:
        if str(oid) not in _d["rewarded"]:
            _d["rewarded"].append(str(oid))
            _save()


def unrewarded_delivered() -> list:
    with _lock:
        rewarded = set(_d["rewarded"])
        return [oid for oid in _d["delivered"] if oid not in rewarded]


def grant(buyer_id, stars: int) -> None:
    if buyer_id is None:
        return
    with _lock:
        _d["pending"][str(buyer_id)] = _d["pending"].get(str(buyer_id), 0) + int(stars)
        _save()


def peek(buyer_id) -> int:
    if buyer_id is None:
        return 0
    return int(_d["pending"].get(str(buyer_id), 0))


def consume(buyer_id) -> int:
    if buyer_id is None:
        return 0
    with _lock:
        n = int(_d["pending"].pop(str(buyer_id), 0))
        _save()
        return n


def snapshot() -> dict:
    with _lock:
        return copy.deepcopy(_d)
