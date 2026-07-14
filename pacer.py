"""
pacer.py — человекоподобные задержки исходящих сообщений, ПО ЧАТУ.

Урок эталона (death-spiral): глобальная очередь + рост задержки от общей глубины
приводили к бесконечному отставанию под флудом. Здесь каждый чат пейсится
независимо: флуд в одном чате не тормозит остальные. Один фоновый диспетчер,
у каждого чата — своя очередь и своё «время следующей отправки».

Проект: ProdX (https://prodx.pro)
Разработчик: Xuisuki — Telegram @Xuisuki, https://github.com/Xuisuki
"""
from __future__ import annotations

import collections
import logging
import random
import threading
import time
from typing import Callable

logger = logging.getLogger("pacer")


def reply_interval(n: int, cfg) -> float:
    """Задержка перед отправкой при глубине очереди ЭТОГО чата = n.
    interval(n) = clamp(MIN, MAX, PER_ORDER*n - OFFSET) + джиттер. Чистая функция."""
    base = cfg.REPLY_DELAY_PER_ORDER * n - cfg.REPLY_DELAY_OFFSET
    base = max(cfg.REPLY_DELAY_MIN, min(base, cfg.REPLY_DELAY_MAX))
    jit = base * cfg.REPLY_JITTER
    return max(cfg.REPLY_DELAY_MIN, base + random.uniform(-jit, jit))


class Pacer:
    def __init__(self, send_fn: Callable[[object, str], None], cfg):
        self._send = send_fn                       # send_fn(chat_id, text)
        self._cfg = cfg
        self._queues: dict = {}                    # chat_id -> deque[str]
        self._next_at: dict = {}                   # chat_id -> ts следующей отправки
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="pacer", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()

    def say(self, chat_id, text: str):
        """Поставить сообщение в очередь чата."""
        with self._lock:
            self._queues.setdefault(chat_id, collections.deque()).append(text)

    def _loop(self):
        while not self._stop.is_set():
            now = time.time()
            sent_any = False
            with self._lock:
                chats = list(self._queues.items())
            for chat_id, q in chats:
                if not q or now < self._next_at.get(chat_id, 0.0):
                    continue
                with self._lock:
                    if not q:
                        continue
                    text = q.popleft()
                    depth = len(q) + 1             # глубина ИМЕННО этого чата
                try:
                    self._send(chat_id, text)
                except Exception:                  # noqa: BLE001
                    logger.exception("pacer send failed for chat %s", chat_id)
                delay = reply_interval(depth, self._cfg) if getattr(self._cfg, "PACER_ENABLED", True) else 0.0
                self._next_at[chat_id] = time.time() + delay
                sent_any = True
            self._stop.wait(0.15 if sent_any else 0.4)
