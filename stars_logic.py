"""
stars_logic.py — чистая, детерминированная логика Funpay-Telegram-Stars.

Здесь только денежно-чувствительные функции без побочных эффектов и без сетевых
вызовов: определение количества звёзд к выдаче, классификация результата отправки
и разбор ошибок Fragment. Всё, что тут лежит, покрыто юнит-тестами (tests/).

Проект: ProdX (https://prodx.pro)
Разработчик: Xuisuki — Telegram @Xuisuki, https://github.com/Xuisuki
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

# Уверенность определения количества звёзд.
CONF_MARKER = "marker"    # явный тег tg_stars:N -> максимальная уверенность
CONF_LABELED = "labeled"  # "N звёзд" / "N stars" / "N ⭐" -> высокая уверенность
CONF_AMBIGUOUS = "ambiguous"  # только голое число или ничего -> НЕ выдаём молча


def normalize_username(username: str) -> str:
    """Приводит тег к каноничному виду без @ и пробелов."""
    return (username or "").strip().lstrip("@").strip()


def extract_per_lot_stars(title: str, description: str = "") -> Tuple[Optional[int], str]:
    """Определить, сколько звёзд соответствует одному лоту.

    Возвращает (count, confidence). count == None означает, что уверенно
    определить не удалось — в этом случае заказ НЕ должен выдаваться автоматически,
    его следует отправить на ручную проверку (NEEDS_REVIEW). Молчаливый дефолт в 50,
    как в исходной версии, приводил к неверной выдаче — тут его нет.
    """
    text = f"{title or ''} {description or ''}".lower()

    # 1) Явный машиночитаемый маркер продавца: tg_stars:500 / tg_stars=500
    m = re.search(r"tg_stars[:=]\s*(\d{1,7})", text)
    if m:
        return int(m.group(1)), CONF_MARKER

    # 2) Число рядом со словом-меткой "звёзд"/"stars"/"⭐" (в любом порядке).
    m = re.search(r"(\d{1,7})\s*(?:зв[её]зд[а-я]*|⭐|stars?)", text)
    if not m:
        m = re.search(r"(?:зв[её]зд[а-я]*|⭐|stars?)\D{0,10}(\d{1,7})", text)
    if m:
        return int(m.group(1)), CONF_LABELED

    # 3) Уверенно определить нельзя. Голое число не берём — оно может быть ценой,
    #    годом, версией и т.п. Пусть решает человек.
    return None, CONF_AMBIGUOUS


def resolve_order_stars(
    title: str,
    description: str,
    order_amount: Optional[int],
    multiply_by_amount: bool = True,
) -> Tuple[Optional[int], str]:
    """Итоговое количество звёзд к выдаче за заказ.

    total = звёзд_на_лот * количество_купленных_лотов (order.amount).
    Исходная версия полностью игнорировала order.amount, из-за чего покупка
    нескольких лотов недовыдавалась. Возвращает (total, reason).
    total == None -> отправить на ручную проверку.
    """
    per_lot, conf = extract_per_lot_stars(title, description)
    if per_lot is None:
        return None, f"не удалось уверенно определить число звёзд (confidence={conf})"

    qty = order_amount if isinstance(order_amount, int) and order_amount > 0 else 1
    if not multiply_by_amount:
        qty = 1

    total = per_lot * qty
    reason = f"{per_lot}/лот x {qty} = {total} (confidence={conf})"
    return total, reason


# --- Приоритетный источник: параметры заказа FunPay (lot_params / buyer_params) ---
# Их отдаёт полный Order из account.get_order() — надёжнее парсинга свободного текста.
_STARS_KEY_RE = re.compile(r"кол-?во|количеств|зв[её]зд|stars?|\bшт\b", re.I)
_USERNAME_KEY_RE = re.compile(r"username|юзер|тег|nick|ник|telegram", re.I)
_NICK_RE = re.compile(r"^[A-Za-z0-9_]{4,32}$")


def is_valid_nick(username: str) -> bool:
    """Формат тега валиден? (Fragment проверит существование при выдаче.)"""
    return bool(_NICK_RE.match(normalize_username(username)))


def stars_from_lot_params(lot_params, order_amount, multiply_by_amount: bool = True) -> Tuple[Optional[int], str]:
    """Кол-во звёзд из параметров лота (список (ключ, значение)), умноженное на order.amount.
    Возвращает (total|None, reason)."""
    for k, v in (lot_params or []):
        if _STARS_KEY_RE.search(f"{k} {v}"):
            m = re.search(r"\d[\d\s.,]*", str(v))
            if m:
                per = int(re.sub(r"\D", "", m.group(0)) or 0)
                if per > 0:
                    qty = order_amount if isinstance(order_amount, int) and order_amount > 0 else 1
                    if not multiply_by_amount:
                        qty = 1
                    return per * qty, f"lot_param '{k}={v}' x{qty} = {per * qty}"
    return None, "в параметрах лота нет количества звёзд"


def username_from_buyer_params(buyer_params) -> Optional[str]:
    """@username, введённый покупателем на чекауте FunPay. None если нет/невалиден."""
    if not isinstance(buyer_params, dict):
        return None
    for k, v in buyer_params.items():          # 1) по имени поля ("Telegram Username")
        if v and _USERNAME_KEY_RE.search(str(k)):
            cand = normalize_username(str(v))
            if _NICK_RE.match(cand):
                return cand
    for v in buyer_params.values():            # 2) любое значение, похожее на тег
        cand = normalize_username(str(v))
        if _NICK_RE.match(cand):
            return cand
    return None


def resolve_order(lot_params, buyer_params, title: str, description: str,
                  order_amount: Optional[int], multiply_by_amount: bool = True):
    """Единый резолвер заказа: сначала параметры заказа, при неудаче — текст.
    Возвращает (stars|None, username|None, reason)."""
    stars, reason = stars_from_lot_params(lot_params, order_amount, multiply_by_amount)
    if stars is None:
        stars, reason = resolve_order_stars(title, description, order_amount, multiply_by_amount)
    username = username_from_buyer_params(buyer_params)
    return stars, username, reason


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    """Убрать ANSI-escape-последовательности (для чистого лога в файл)."""
    return _ANSI_RE.sub("", text)
