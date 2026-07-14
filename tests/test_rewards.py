"""Тесты бонуса за отзыв. Прогон: pytest -q tests/test_rewards.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rewards as R  # noqa: E402


def _isolate(tmp_path):
    """Изолировать модуль: свой файл + чистое состояние."""
    R._PATH = str(tmp_path / "rewards.json")
    R._d = R._fresh()


def test_grant_peek_consume(tmp_path):
    _isolate(tmp_path)
    assert R.peek(42) == 0
    R.grant(42, 1)
    R.grant(42, 2)
    assert R.peek(42) == 3
    assert R.consume(42) == 3
    assert R.peek(42) == 0          # обнулилось


def test_review_flow(tmp_path):
    _isolate(tmp_path)
    R.record_delivery("ORD1", 7)
    assert R.buyer_of("ORD1") == 7
    assert not R.already_rewarded("ORD1")
    # отзыв пойман -> помечаем и начисляем бонус покупателю
    R.add_rewarded("ORD1")
    R.grant(7, 1)
    assert R.already_rewarded("ORD1")
    assert "ORD1" not in R.unrewarded_delivered()
    assert R.peek(7) == 1


def test_add_rewarded_idempotent(tmp_path):
    _isolate(tmp_path)
    R.add_rewarded("X")
    R.add_rewarded("X")
    assert R.snapshot()["rewarded"].count("X") == 1


def test_none_buyer_safe(tmp_path):
    _isolate(tmp_path)
    R.record_delivery("O", None)   # не падает
    R.grant(None, 5)
    assert R.peek(None) == 0
    assert R.consume(None) == 0
