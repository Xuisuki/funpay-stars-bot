"""Тесты реестра заказов. Прогон: pytest -q tests/test_ledger.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ledger as L  # noqa: E402


def _fresh(tmp_path, name="orders.db"):
    return L.OrderLedger(str(tmp_path / name))


def test_create_is_idempotent(tmp_path):
    lg = _fresh(tmp_path)
    assert lg.create_order("100", buyer_id=1, chat_id=9, stars=50) is True
    # Повторная регистрация того же заказа -> False, состояние не сбрасывается.
    assert lg.create_order("100", buyer_id=1, chat_id=9, stars=999) is False
    o = lg.get("100")
    assert o["state"] == L.AWAITING_NICK
    assert o["stars"] == 50  # не перезатёрлось на 999


def test_active_by_buyer(tmp_path):
    lg = _fresh(tmp_path)
    lg.create_order("1", 42, 9, 50)
    assert lg.get_active_by_buyer(42)["order_id"] == "1"
    lg.set_awaiting_confirmation("1", "durov")
    assert lg.get_active_by_buyer(42)["state"] == L.AWAITING_CONFIRMATION
    lg.try_begin_delivery("1")
    lg.mark_delivered("1", "durov", 50)
    # Доставленный заказ больше не активен.
    assert lg.get_active_by_buyer(42) is None


def test_delivery_guard_only_once(tmp_path):
    """Главный инвариант идемпотентности: доставку можно захватить только раз."""
    lg = _fresh(tmp_path)
    lg.create_order("7", 1, 9, 100)
    lg.set_awaiting_confirmation("7", "user")
    assert lg.try_begin_delivery("7") is True   # первый захват
    assert lg.try_begin_delivery("7") is False  # уже DELIVERING -> отказ
    lg.mark_delivered("7", "user", 100)
    assert lg.try_begin_delivery("7") is False  # доставлен -> отказ


def test_failed_can_be_retried(tmp_path):
    lg = _fresh(tmp_path)
    lg.create_order("8", 1, 9, 100)
    lg.set_awaiting_confirmation("8", "user")
    assert lg.try_begin_delivery("8") is True
    lg.mark_failed("8", "insufficient balance")
    # Из FAILED повторная доставка разрешена (напр. после пополнения).
    assert lg.try_begin_delivery("8") is True


def test_needs_review_blocks_redelivery(tmp_path):
    lg = _fresh(tmp_path)
    lg.create_order("9", 1, 9, 100)
    lg.set_awaiting_confirmation("9", "user")
    lg.try_begin_delivery("9")
    lg.mark_needs_review("9", "timeout")
    # NEEDS_REVIEW не разрешает авто-повтор (только ручное вмешательство).
    assert lg.try_begin_delivery("9") is False


def test_persistence_across_reopen(tmp_path):
    lg = _fresh(tmp_path)
    lg.create_order("55", 1, 9, 50)
    lg.set_awaiting_confirmation("55", "user")
    lg.close()
    # Открываем заново тот же файл — состояние на месте.
    lg2 = L.OrderLedger(str(tmp_path / "orders.db"))
    o = lg2.get("55")
    assert o is not None and o["state"] == L.AWAITING_CONFIRMATION
    assert o["username"] == "user"


def test_stuck_deliveries_detection(tmp_path, monkeypatch):
    lg = _fresh(tmp_path)
    lg.create_order("77", 1, 9, 50)
    lg.set_awaiting_confirmation("77", "user")
    lg.try_begin_delivery("77")  # -> DELIVERING сейчас
    # Сразу не считается зависшим.
    assert lg.stuck_deliveries(older_than_seconds=120) == []
    # Подменяем время: как будто прошло много.
    monkeypatch.setattr(L, "_now", lambda: __import__("time").time() + 10_000)
    stuck = lg.stuck_deliveries(older_than_seconds=120)
    assert len(stuck) == 1 and stuck[0]["order_id"] == "77"


def test_audit_records_money_events(tmp_path):
    lg = _fresh(tmp_path)
    lg.create_order("3", 1, 9, 50)
    lg.set_awaiting_confirmation("3", "user")
    lg.try_begin_delivery("3")
    lg.mark_delivered("3", "user", 50)
    rows = lg._conn.execute(
        "SELECT event FROM audit WHERE order_id='3' ORDER BY id"
    ).fetchall()
    events = [r["event"] for r in rows]
    assert "ORDER_CREATED" in events
    assert "MONEY_DELIVERED" in events


def test_counts(tmp_path):
    lg = _fresh(tmp_path)
    lg.create_order("a", 1, 9, 50)
    lg.create_order("b", 2, 9, 50)
    lg.set_awaiting_confirmation("b", "u")
    lg.try_begin_delivery("b")
    lg.mark_delivered("b", "u", 50)
    c = lg.counts()
    assert c.get(L.AWAITING_NICK) == 1
    assert c.get(L.DELIVERED) == 1
