"""
fragment_stars.py — синхронный фасад над вендорной PyFragment (self-hosted).

Seed-фраза используется ТОЛЬКО локально для подписи TON-транзакции (через tonutils),
наружу не уходит. Аудит либы: bohd4nx/FragmentAPI @3d0cf38.
DRY_RUN=true имитирует покупку без обращения к сети.

pyfragment импортируется ЛЕНИВО (внутри функций), поэтому модуль можно импортировать
и тестировать без установленного tonutils.

Проект: ProdX (https://prodx.pro)
Разработчик: Xuisuki — Telegram @Xuisuki, https://github.com/Xuisuki
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import config

logger = logging.getLogger("fragment")

# Категории результата для оркестратора:
#   ok / bad_username / low_balance / cookies / kyc / tx_failed / config / other


@dataclass
class StarsResult:
    ok: bool
    category: str
    message: str = ""
    transaction_id: Optional[str] = None
    amount: Optional[int] = None


def _classify(exc: Exception) -> tuple[str, str]:
    from pyfragment.exceptions import (
        UserNotFoundError, WalletError, CookieError, FragmentPageError,
        VerificationError, TransactionError, ConfigurationError,
    )
    msg = str(exc)
    if isinstance(exc, UserNotFoundError):
        return "bad_username", msg
    if isinstance(exc, WalletError):
        if "insufficient" in msg.lower() or "balance" in msg.lower():
            return "low_balance", msg
        return "other", msg
    if isinstance(exc, (CookieError, FragmentPageError)):
        return "cookies", msg
    if isinstance(exc, VerificationError):
        return "kyc", msg
    if isinstance(exc, TransactionError):
        return "tx_failed", msg
    if isinstance(exc, ConfigurationError):
        return "config", msg
    return "other", msg


def _cookies_obj():
    """Куки в .env лежат строкой 'k=v; k=v'. PyFragment хочет dict (или JSON-строку)."""
    raw = config.FRAGMENT_COOKIES.strip()
    if raw[:1] in ("{", "["):
        return raw
    d = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def _build_client():
    from pyfragment import FragmentClient
    return FragmentClient(
        seed=config.FRAGMENT_SEED,
        api_key=config.TON_API_KEY,
        cookies=_cookies_obj(),
        wallet_version=config.FRAGMENT_WALLET_VERSION,
    )


async def _wallet_async() -> dict:
    async with _build_client() as client:
        w = await client.get_wallet()
    return {
        "address": str(getattr(w, "address", "")),
        "state": getattr(w, "state", None),
        "ton": float(getattr(w, "ton_balance", 0) or 0),
        "usdt": float(getattr(w, "usdt_balance", 0) or 0),
    }


def get_wallet_info() -> dict:
    """Адрес + балансы TON/USDT. Read-only — работает и в DRY_RUN (реальный баланс)."""
    try:
        return asyncio.run(_wallet_async())
    except Exception as e:  # noqa: BLE001
        cat, msg = _classify(e)
        logger.error("get_wallet_info FAILED [%s]: %s", cat, msg)
        return {"error": cat, "message": msg}


async def _purchase_async(username: str, amount: int) -> StarsResult:
    async with _build_client() as client:
        res = await client.purchase_stars(
            username,
            amount,
            show_sender=config.FRAGMENT_SHOW_SENDER,
            payment_method=config.FRAGMENT_PAYMENT_METHOD,
        )
    return StarsResult(
        ok=True,
        category="ok",
        message="ok",
        transaction_id=getattr(res, "transaction_id", None),
        amount=getattr(res, "amount", amount),
    )


async def _balance_async() -> float:
    async with _build_client() as client:
        info = await client.get_wallet()
    return float(getattr(info, "ton_balance", 0.0) or 0.0)


def buy_stars(username: str, amount: int) -> StarsResult:
    """Купить `amount` звёзд на @username. Блокирующий вызов (для воркер-потока)."""
    username = username.lstrip("@").strip()
    if config.DRY_RUN:
        logger.info("[DRY_RUN] purchase_stars(@%s, %s) -> имитация успеха", username, amount)
        return StarsResult(ok=True, category="ok", message="dry-run",
                           transaction_id="DRYRUN", amount=amount)
    try:
        return asyncio.run(_purchase_async(username, amount))
    except Exception as e:  # noqa: BLE001
        cat, msg = _classify(e)
        logger.error("purchase_stars(@%s, %s) FAILED [%s]: %s", username, amount, cat, msg)
        return StarsResult(ok=False, category=cat, message=msg)


def get_ton_balance() -> Optional[float]:
    """Баланс TON кошелька. None при ошибке. В DRY_RUN отдаёт 999.0."""
    if config.DRY_RUN:
        return 999.0
    try:
        return asyncio.run(_balance_async())
    except Exception as e:  # noqa: BLE001
        logger.error("get_ton_balance FAILED: %s", e)
        return None
