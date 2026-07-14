"""
alerts.py — Telegram-алерты оператору (споры, возвраты, протухшие куки, сбои,
низкий баланс) + приём команд от админа. Транспорт — прямой Telegram Bot API
через requests, отдельный bot-токен (@BotFather), НЕ FunPay.

Проект: ProdX (https://prodx.pro)
Разработчик: Xuisuki — Telegram @Xuisuki, https://github.com/Xuisuki
"""
from __future__ import annotations

import logging
import time

import requests

import config

logger = logging.getLogger("alerts")


def send_to(chat_id, text: str) -> None:
    """Ответ в конкретный чат (для команд)."""
    if not config.TELEGRAM_BOT_TOKEN:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=10,
        )
    except Exception as e:  # noqa: BLE001
        logger.error("send_to %s failed: %s", chat_id, e)


def poll_commands(handler) -> None:
    """Long-poll getUpdates; вызывает handler(text, chat_id) для сообщений от админов."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_ADMIN_IDS:
        logger.warning("poll_commands: Telegram не настроен — команды недоступны")
        return
    base = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"
    admins = set(config.TELEGRAM_ADMIN_IDS)
    offset = None
    while True:
        try:
            params = {"timeout": 25}
            if offset is not None:
                params["offset"] = offset
            r = requests.get(base + "/getUpdates", params=params, timeout=35)
            for upd in r.json().get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message") or {}
                frm = (msg.get("from") or {}).get("id")
                chat_id = (msg.get("chat") or {}).get("id")
                text = (msg.get("text") or "").strip()
                if frm in admins and text:
                    try:
                        handler(text, chat_id)
                    except Exception as e:  # noqa: BLE001
                        logger.error("cmd handler error: %s", e)
        except Exception as e:  # noqa: BLE001
            logger.error("poll_commands error: %s", e)
            time.sleep(5)


def send(text: str) -> None:
    """Отправить алерт всем админам. Тихо логирует при отсутствии настроек/ошибке."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_ADMIN_IDS:
        logger.warning("ALERT (Telegram не настроен): %s", text)
        return
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    for chat_id in config.TELEGRAM_ADMIN_IDS:
        try:
            r = requests.post(
                url,
                json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
                timeout=10,
            )
            if r.status_code != 200:
                logger.error("alert to %s failed: HTTP %s %s", chat_id, r.status_code, r.text[:200])
        except Exception as e:  # noqa: BLE001
            logger.error("alert to %s exception: %s", chat_id, e)
