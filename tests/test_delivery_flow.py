"""Интеграционные тесты денежного пути (self-hosted Fragment + категории ошибок).

Fragment (fs.buy_stars), FunPay и пейсер заменены фейками — сети нет.
Проверяем маппинг категорий Fragment -> состояния реестра и денежные инварианты.
Прогон: pytest -q tests/test_delivery_flow.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ledger as L          # noqa: E402
import bot_fragment as bot  # noqa: E402
import rewards as R         # noqa: E402
import stats as S           # noqa: E402
from fragment_stars import StarsResult  # noqa: E402


class FakePacer:
    def __init__(self):
        self.msgs = []

    def say(self, chat_id, text):
        self.msgs.append((chat_id, text))


class FakeBoard:
    def __init__(self):
        self.orders = []
        self.state = {}

    def push_order(self, *a):
        self.orders.append(a)

    def set(self, **k):
        self.state.update(k)

    def push_log(self, line):
        pass


class FakeAccount:
    id = 999

    def __init__(self):
        self.refunded = []

    def refund(self, oid):
        self.refunded.append(oid)

    def get_my_subcategory_lots(self, cid):
        return []

    def send_message(self, cid, txt):
        pass


def _ctx(tmp_path, name="o.db"):
    R._PATH = str(tmp_path / "rewards.json"); R._d = R._fresh()
    S._PATH = str(tmp_path / "stats.json"); S._d = S._fresh()
    lg = L.OrderLedger(str(tmp_path / name))
    pacer = FakePacer()
    board = FakeBoard()
    acc = FakeAccount()
    ctx = bot.Ctx(account=acc, ledger=lg, pacer=pacer, board=board, executor=None)
    return ctx


def _order(ctx, oid="1", stars=50, user="durov"):
    ctx.ledger.create_order(oid, buyer_id=5, chat_id=7, stars=stars)
    ctx.ledger.set_awaiting_confirmation(oid, user)


def _patch_buy(monkeypatch, category, ok=False, tx=None):
    monkeypatch.setattr(bot.fs, "buy_stars",
                        lambda u, q: StarsResult(ok=ok, category=category, message=category, transaction_id=tx, amount=q))


def _msgs(ctx):
    return [t for _, t in ctx.pacer.msgs]


def test_ok_delivered(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path); _order(ctx)
    _patch_buy(monkeypatch, "ok", ok=True, tx="TX123")
    bot.deliver(ctx, "1", 7, 5, "durov", 50)
    assert ctx.ledger.get("1")["state"] == L.DELIVERED
    assert ctx.account.refunded == []
    assert any("Готово" in m for m in _msgs(ctx))


def test_tx_failed_needs_review_no_refund(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path); _order(ctx)
    _patch_buy(monkeypatch, "tx_failed")
    bot.deliver(ctx, "1", 7, 5, "durov", 50)
    assert ctx.ledger.get("1")["state"] == L.NEEDS_REVIEW
    assert ctx.account.refunded == []          # неоднозначно -> НЕ возвращаем


def test_cookies_needs_review(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path); _order(ctx)
    _patch_buy(monkeypatch, "cookies")
    bot.deliver(ctx, "1", 7, 5, "durov", 50)
    assert ctx.ledger.get("1")["state"] == L.NEEDS_REVIEW
    assert ctx.account.refunded == []


def test_low_balance_refunds_when_enabled(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path); _order(ctx)
    monkeypatch.setattr(bot.config, "AUTO_REFUND_ON_FAIL", True)
    monkeypatch.setattr(bot.config, "AUTO_DEACTIVATE", False)
    _patch_buy(monkeypatch, "low_balance")
    bot.deliver(ctx, "1", 7, 5, "durov", 50)
    assert ctx.ledger.get("1")["state"] == L.REFUNDED
    assert ctx.account.refunded == ["1"]


def test_low_balance_no_autorefund(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path); _order(ctx)
    monkeypatch.setattr(bot.config, "AUTO_REFUND_ON_FAIL", False)
    monkeypatch.setattr(bot.config, "AUTO_DEACTIVATE", False)
    _patch_buy(monkeypatch, "low_balance")
    bot.deliver(ctx, "1", 7, 5, "durov", 50)
    assert ctx.ledger.get("1")["state"] == L.FAILED
    assert ctx.account.refunded == []


def test_bad_username_reasks_no_refund(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path); _order(ctx)
    _patch_buy(monkeypatch, "bad_username")
    bot.deliver(ctx, "1", 7, 5, "durov", 50)
    # не возврат, а возврат заказа на пере-ввод ника
    assert ctx.ledger.get("1")["state"] == L.AWAITING_NICK
    assert ctx.account.refunded == []
    assert any("корректный тег" in m for m in _msgs(ctx))


def test_idempotent_single_send(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path); _order(ctx)
    calls = {"n": 0}

    def buy(u, q):
        calls["n"] += 1
        return StarsResult(ok=True, category="ok", transaction_id="T", amount=q)

    monkeypatch.setattr(bot.fs, "buy_stars", buy)
    bot.deliver(ctx, "1", 7, 5, "durov", 50)
    assert calls["n"] == 1
    # второй заход захватить доставку не сможет -> buy_stars не вызовется снова
    bot.deliver(ctx, "1", 7, 5, "durov", 50)
    assert calls["n"] == 1


def test_review_bonus_added_to_delivery(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path); _order(ctx, stars=50)
    R.grant(5, 1)                       # покупателю 5 висит бонус +1
    captured = {}

    def buy(u, q):
        captured["q"] = q
        return StarsResult(ok=True, category="ok", transaction_id="T", amount=q)

    monkeypatch.setattr(bot.fs, "buy_stars", buy)
    bot.deliver(ctx, "1", 7, 5, "durov", 50)
    assert captured["q"] == 51          # 50 + бонус 1
    assert R.peek(5) == 0               # бонус потреблён
