"""Тесты чистой денежной логики. Прогон: pytest -q tests/test_stars_logic.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import stars_logic as sl  # noqa: E402


# ---- extract_per_lot_stars ------------------------------------------------
def test_marker_wins():
    n, conf = sl.extract_per_lot_stars("Звёзды tg_stars:500 быстро", "цена 100р")
    assert n == 500 and conf == sl.CONF_MARKER


def test_labeled_number_before_word():
    n, conf = sl.extract_per_lot_stars("Куплю 250 звёзд Telegram", "")
    assert n == 250 and conf == sl.CONF_LABELED


def test_labeled_stars_word():
    n, conf = sl.extract_per_lot_stars("100 stars pack", "")
    assert n == 100 and conf == sl.CONF_LABELED


def test_labeled_emoji():
    n, conf = sl.extract_per_lot_stars("Донат 75 ⭐", "")
    assert n == 75 and conf == sl.CONF_LABELED


def test_bare_number_is_ambiguous_not_50():
    # Ключевой кейс: голое число (цена/год) НЕ должно молча выдаваться.
    n, conf = sl.extract_per_lot_stars("Telegram premium 2024", "цена 349")
    assert n is None and conf == sl.CONF_AMBIGUOUS


def test_empty_is_ambiguous():
    n, _conf = sl.extract_per_lot_stars("", "")
    assert n is None


# ---- resolve_order_stars --------------------------------------------------
def test_resolve_multiplies_by_amount():
    total, reason = sl.resolve_order_stars("50 звёзд", "", order_amount=3)
    assert total == 150, reason


def test_resolve_amount_none_defaults_to_one():
    total, _ = sl.resolve_order_stars("tg_stars:50", "", order_amount=None)
    assert total == 50


def test_resolve_no_multiply_flag():
    total, _ = sl.resolve_order_stars("50 звёзд", "", order_amount=4,
                                      multiply_by_amount=False)
    assert total == 50


def test_resolve_ambiguous_returns_none():
    total, reason = sl.resolve_order_stars("просто товар", "описание", order_amount=1)
    assert total is None and "не удалось" in reason


# ---- utils ----------------------------------------------------------------
def test_normalize_username():
    assert sl.normalize_username("  @Durov ") == "Durov"


def test_strip_ansi():
    assert sl.strip_ansi("\x1b[32mОК\x1b[0m") == "ОК"


# ---- lot_params / buyer_params (приоритетный путь) ----
def test_stars_from_lot_params_multiplies():
    lp = [("Количество звёзд", "50 звёзд"), ("Способ получения", "По username")]
    total, reason = sl.stars_from_lot_params(lp, order_amount=3)
    assert total == 150, reason


def test_stars_from_lot_params_none_when_absent():
    lp = [("Способ получения", "По username")]
    total, _ = sl.stars_from_lot_params(lp, order_amount=1)
    assert total is None


def test_stars_from_lot_params_empty():
    assert sl.stars_from_lot_params([], 1)[0] is None
    assert sl.stars_from_lot_params(None, 1)[0] is None


def test_username_from_buyer_params_by_key():
    # регистр покупателя сохраняется (Fragment принимает регистронезависимо)
    assert sl.username_from_buyer_params({"Telegram Username": "mawLikow"}) == "mawLikow"


def test_username_from_buyer_params_with_at():
    assert sl.username_from_buyer_params({"Тег в телеграм": "@durov"}) == "durov"


def test_username_from_buyer_params_value_fallback():
    # ключ не намекает на ник, но значение похоже на тег
    assert sl.username_from_buyer_params({"Поле": "vpotoke_15"}) == "vpotoke_15"


def test_username_from_buyer_params_none():
    assert sl.username_from_buyer_params({"Игра": "Dota 2"}) is None
    assert sl.username_from_buyer_params(None) is None


def test_resolve_order_prefers_params():
    stars, user, reason = sl.resolve_order(
        lot_params=[("Количество звёзд", "100 звёзд")],
        buyer_params={"Telegram Username": "durov"},
        title="любой текст", description="", order_amount=2,
    )
    assert stars == 200 and user == "durov", reason


def test_resolve_order_text_fallback_when_no_params():
    stars, user, _ = sl.resolve_order(
        lot_params=[], buyer_params={},
        title="50 звёзд Telegram", description="", order_amount=1,
    )
    assert stars == 50 and user is None
