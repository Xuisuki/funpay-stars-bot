"""Тесты per-chat пейсера. Прогон: pytest -q tests/test_pacer.py"""
import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pacer as P  # noqa: E402


def _cfg(**over):
    base = dict(REPLY_DELAY_MIN=15, REPLY_DELAY_PER_ORDER=18.0, REPLY_DELAY_OFFSET=30.0,
                REPLY_DELAY_MAX=600, REPLY_JITTER=0.0, PACER_ENABLED=True)
    base.update(over)
    return SimpleNamespace(**base)


def test_interval_clamps_low():
    # 18*1-30 = -12 -> зажимается к MIN=15
    assert P.reply_interval(1, _cfg()) == 15


def test_interval_mid():
    assert P.reply_interval(5, _cfg()) == 60      # 18*5-30 = 60


def test_interval_clamps_high():
    assert P.reply_interval(100, _cfg()) == 600    # зажим к MAX


def test_interval_jitter_within_bounds():
    cfg = _cfg(REPLY_JITTER=0.15)
    for _ in range(50):
        v = P.reply_interval(5, cfg)               # база 60, джиттер +-15%
        assert 15 <= v <= 69


def test_pacer_delivers_all_when_disabled():
    sent = []
    pc = P.Pacer(lambda cid, txt: sent.append((cid, txt)), _cfg(PACER_ENABLED=False))
    pc.say(1, "a")
    pc.say(1, "b")
    pc.say(2, "c")
    pc.start()
    deadline = time.time() + 3
    while len(sent) < 3 and time.time() < deadline:
        time.sleep(0.05)
    pc.stop()
    assert sorted(t for _, t in sent) == ["a", "b", "c"]


def test_pacer_per_chat_independence():
    # Чат 1 «заморожен» большой задержкой, чат 2 должен доставиться сразу.
    sent = []
    cfg = _cfg(PACER_ENABLED=True, REPLY_DELAY_MIN=100, REPLY_DELAY_MAX=100)
    pc = P.Pacer(lambda cid, txt: sent.append((cid, txt)), cfg)
    pc.say(1, "x1")   # уйдёт сразу (первое сообщение чата), потом чат 1 «замёрзнет» на 100с
    pc.say(1, "x2")   # застрянет
    pc.say(2, "y1")   # чат 2 не должен ждать чат 1
    pc.start()
    deadline = time.time() + 3
    while {"y1"} - {t for _, t in sent} and time.time() < deadline:
        time.sleep(0.05)
    pc.stop()
    delivered = [t for _, t in sent]
    assert "y1" in delivered      # чат 2 доставлен, несмотря на заморозку чата 1
    assert "x2" not in delivered  # чат 1 всё ещё под задержкой
