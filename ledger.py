"""
ledger.py — персистентный идемпотентный реестр заказов Funpay-Telegram-Stars.

Зачем: исходная версия держала состояние заказов в обычном dict в памяти. Любой
рестарт/краш терял оплаченные, но не выданные заказы, а на неоднозначном ответе
Fragment бот мог выдать звёзды и вернуть деньги (двойная потеря). Реестр на SQLite
даёт три вещи, критичные для платёжной логики:

  1. Персистентность — состояние переживает рестарт.
  2. Идемпотентность — на один order_id звёзды уходят ровно один раз (атомарный
     переход в DELIVERING через UPDATE ... WHERE state IN (...)).
  3. Аудит — append-only журнал каждой выдачи/возврата с суммами для разбора споров.

Модуль не зависит от FunPayAPI и тестируется в изоляции (tests/test_ledger.py).

Проект: ProdX (https://prodx.pro)
Разработчик: Xuisuki — Telegram @Xuisuki, https://github.com/Xuisuki
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

# ---- Состояния заказа (стейт-машина) --------------------------------------
AWAITING_NICK = "AWAITING_NICK"                # заказ создан, ждём @username
AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"  # ник провалидирован, ждём "+"
DELIVERING = "DELIVERING"                      # идёт отправка в Fragment
DELIVERED = "DELIVERED"                        # звёзды доставлены
FAILED = "FAILED"                              # явная ошибка, отправки не было
NEEDS_REVIEW = "NEEDS_REVIEW"                  # неоднозначно, нужна ручная проверка
REFUNDED = "REFUNDED"                          # средства возвращены

# Активные состояния, в которых заказ ждёт действий покупателя.
ACTIVE_STATES = (AWAITING_NICK, AWAITING_CONFIRMATION)
# Из этих состояний разрешено начинать доставку.
DELIVERABLE_FROM = (AWAITING_CONFIRMATION, FAILED)
# Терминальные состояния.
TERMINAL_STATES = (DELIVERED, REFUNDED)


def _now() -> int:
    return int(time.time())


class OrderLedger:
    def __init__(self, db_path: str = "orders.db"):
        self.db_path = db_path
        self._lock = threading.RLock()
        # check_same_thread=False + внешний RLock: одно соединение безопасно для
        # однопоточного цикла бота и опциональных фоновых потоков (монитор баланса).
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    order_id   TEXT PRIMARY KEY,
                    buyer_id   INTEGER,
                    chat_id    INTEGER,
                    stars      INTEGER,
                    username   TEXT,
                    state      TEXT NOT NULL,
                    attempts   INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts       INTEGER NOT NULL,
                    order_id TEXT,
                    event    TEXT NOT NULL,
                    detail   TEXT
                );
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_orders_buyer ON orders(buyer_id, state);"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_orders_state ON orders(state);"
            )

    # ---- аудит ------------------------------------------------------------
    def audit(self, order_id: Optional[str], event: str, detail: Any = None) -> None:
        payload = None
        if detail is not None:
            try:
                payload = json.dumps(detail, ensure_ascii=False, default=str)
            except Exception:
                payload = str(detail)
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO audit (ts, order_id, event, detail) VALUES (?,?,?,?)",
                (_now(), order_id, event, payload),
            )

    # ---- заказы -----------------------------------------------------------
    def create_order(
        self, order_id: str, buyer_id: int, chat_id: int, stars: Optional[int]
    ) -> bool:
        """Зарегистрировать новый заказ. Идемпотентно: повторный вызов на уже
        известный order_id НЕ сбрасывает состояние и возвращает False. True — если
        заказ действительно новый (нужно поприветствовать покупателя)."""
        order_id = str(order_id)
        ts = _now()
        with self._lock, self._conn:
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO orders
                    (order_id, buyer_id, chat_id, stars, username, state,
                     attempts, last_error, created_at, updated_at)
                VALUES (?,?,?,?,?,?,0,NULL,?,?)
                """,
                (order_id, buyer_id, chat_id, stars, None, AWAITING_NICK, ts, ts),
            )
            is_new = cur.rowcount == 1
        if is_new:
            self.audit(order_id, "ORDER_CREATED",
                       {"buyer_id": buyer_id, "chat_id": chat_id, "stars": stars})
        return is_new

    def get(self, order_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM orders WHERE order_id=?", (str(order_id),)
            ).fetchone()
        return dict(row) if row else None

    def get_active_by_buyer(self, buyer_id: int) -> Optional[Dict[str, Any]]:
        """Самый свежий заказ покупателя, ожидающий его действий (ник/подтверждение)."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT * FROM orders
                WHERE buyer_id=? AND state IN (?, ?)
                ORDER BY created_at DESC LIMIT 1
                """,
                (buyer_id, AWAITING_NICK, AWAITING_CONFIRMATION),
            ).fetchone()
        return dict(row) if row else None

    def _set(self, order_id: str, state: str, event: str, **fields: Any) -> None:
        cols = ["state=?", "updated_at=?"]
        vals: List[Any] = [state, _now()]
        for k in ("username", "stars", "last_error"):
            if k in fields:
                cols.append(f"{k}=?")
                vals.append(fields[k])
        vals.append(str(order_id))
        with self._lock, self._conn:
            self._conn.execute(
                f"UPDATE orders SET {', '.join(cols)} WHERE order_id=?", vals
            )
        self.audit(order_id, event, {"state": state, **fields})

    def set_awaiting_confirmation(self, order_id: str, username: str) -> None:
        self._set(order_id, AWAITING_CONFIRMATION, "NICK_CONFIRMED", username=username)

    def require_new_nick(self, order_id: str, reason: str = "") -> None:
        """Вернуть заказ на пере-ввод ника (напр. Fragment не нашёл @username)."""
        self._set(order_id, AWAITING_NICK, "RENICK", username=None, last_error=str(reason)[:500])

    def try_begin_delivery(self, order_id: str) -> bool:
        """Атомарно захватить право на доставку. Возвращает True ровно один раз для
        заказа, пока он не доставлен: переход в DELIVERING разрешён только из
        DELIVERABLE_FROM. Это и есть страховка от повторной отправки (идемпотентность)."""
        order_id = str(order_id)
        placeholders = ",".join("?" for _ in DELIVERABLE_FROM)
        with self._lock, self._conn:
            cur = self._conn.execute(
                f"""
                UPDATE orders
                SET state=?, attempts=attempts+1, updated_at=?
                WHERE order_id=? AND state IN ({placeholders})
                """,
                (DELIVERING, _now(), order_id, *DELIVERABLE_FROM),
            )
            acquired = cur.rowcount == 1
        self.audit(order_id, "DELIVERY_BEGIN", {"acquired": acquired})
        return acquired

    def mark_delivered(self, order_id: str, username: str, stars: int,
                       detail: Any = None) -> None:
        self._set(order_id, DELIVERED, "DELIVERED",
                  username=username, stars=stars, last_error=None)
        self.audit(order_id, "MONEY_DELIVERED",
                   {"username": username, "stars": stars, "detail": detail})

    def mark_failed(self, order_id: str, error: str) -> None:
        self._set(order_id, FAILED, "FAILED", last_error=str(error)[:500])

    def mark_needs_review(self, order_id: str, error: str) -> None:
        self._set(order_id, NEEDS_REVIEW, "NEEDS_REVIEW", last_error=str(error)[:500])
        self.audit(order_id, "MONEY_NEEDS_REVIEW", {"error": str(error)[:500]})

    def mark_refunded(self, order_id: str, reason: str = "") -> None:
        self._set(order_id, REFUNDED, "REFUNDED", last_error=str(reason)[:500])
        self.audit(order_id, "MONEY_REFUNDED", {"reason": str(reason)[:500]})

    # ---- отчётность / реконсиляция ---------------------------------------
    def list_by_state(self, state: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM orders WHERE state=? ORDER BY updated_at DESC LIMIT ?",
                (state, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def stuck_deliveries(self, older_than_seconds: int = 120) -> List[Dict[str, Any]]:
        """Заказы, зависшие в DELIVERING дольше порога (краш посреди отправки)."""
        cutoff = _now() - older_than_seconds
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM orders WHERE state=? AND updated_at < ?",
                (DELIVERING, cutoff),
            ).fetchall()
        return [dict(r) for r in rows]

    def counts(self) -> Dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT state, COUNT(*) c FROM orders GROUP BY state"
            ).fetchall()
        return {r["state"]: r["c"] for r in rows}

    def close(self) -> None:
        with self._lock:
            self._conn.close()
