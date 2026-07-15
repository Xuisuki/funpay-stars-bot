"""
dashboard.py — анимированный терминальный дашборд (Rich).

- Анимированный интро-баннер с брендом ОПЕРАТОРА (config.BRAND_NAME; если пусто —
  имя FunPay-аккаунта или "STARS BOT"). Градиентная волна по буквам.
- Живая панель: статус FunPay, баланс Fragment, счётчики реестра заказов,
  последние заказы, хвост лога.
- Кредит-строка (фиксированная): ProdX (prodx.pro) | dev @Xuisuki · @mawlikow.

Проект: ProdX (https://prodx.pro)
Разработчики: @Xuisuki + @mawlikow — github.com/Xuisuki, github.com/mawlikow
"""
from __future__ import annotations

import threading
import time
from collections import deque

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

import config

# «Ионная» палитра для градиентной волны баннера.
_GRADIENT = ["#38bdf8", "#22d3ee", "#67e8f9", "#a5f3fc", "#c4b5fd", "#a78bfa", "#818cf8"]


def _brand_title(funpay_name: str | None = None) -> str:
    return (config.BRAND_NAME or funpay_name or "STARS BOT").upper()


def _credit_line() -> Text:
    t = Text(justify="center")
    t.append("by ", style="grey50")
    t.append(config.CREATOR, style="bold #a78bfa")
    t.append(f" · {config.CREATOR_URL}", style="#818cf8")
    t.append("   |   dev ", style="grey50")
    t.append(config.DEV_TELEGRAM, style="bold #22d3ee")
    t.append(" · ", style="grey50")
    t.append(config.DEV2_TELEGRAM, style="bold #22d3ee")
    return t


def _banner(title: str, phase: float = 0.0) -> Panel:
    """Баннер бренда с бегущей градиентной подсветкой (phase 0..1)."""
    spaced = "  ".join(title)
    text = Text(justify="center")
    n = max(1, len(spaced))
    head = int(phase * (n + 6)) - 3           # позиция «гребня» волны
    for i, ch in enumerate(spaced):
        dist = abs(i - head)
        if dist <= 3:
            color = _GRADIENT[min(dist, len(_GRADIENT) - 1)]
            text.append(ch, style=f"bold {color}")
        else:
            text.append(ch, style="bold #3b4252")
    sub = Text(config.BRAND_TAGLINE or "Telegram Stars · FunPay автовыдача", style="italic grey62", justify="center")
    return Panel(
        Align.center(Group(Text(""), text, Text(""), sub, Text(""), _credit_line())),
        box=box.DOUBLE, border_style="#22d3ee", padding=(1, 4),
    )


def animate_intro(funpay_name: str | None = None, frames: int = 26, duration: float = 1.6,
                  console: Console | None = None) -> None:
    """Проиграть анимированный баннер один раз при старте."""
    from rich.live import Live
    console = console or Console()
    title = _brand_title(funpay_name)
    delay = duration / max(1, frames)
    try:
        with Live(console=console, refresh_per_second=30, transient=False) as live:
            for f in range(frames + 6):
                live.update(_banner(title, f / frames))
                time.sleep(delay)
    except Exception:
        console.print(_banner(title, 0.5))       # не-tty / ошибка — просто финальный кадр


def _dot(ok: bool) -> Text:
    return Text("● ", style="bold green3" if ok else "bold red3")


class Dashboard:
    """Живой дашборд. Бот обновляет state/логи, дашборд рендерит."""

    def __init__(self, ledger=None, funpay_name: str | None = None, maxlog: int = 10):
        self.ledger = ledger
        self.funpay_name = funpay_name
        self.state: dict = {"funpay_online": False, "ton": None, "usdt": None,
                            "dry_run": config.DRY_RUN, "paused": False}
        self.logs: deque = deque(maxlen=maxlog)
        self.recent: deque = deque(maxlen=6)       # (time, kind, order_id, stars, user)
        self._live = None
        self._thread = None
        self._stop = threading.Event()

    # --- обновления от бота ---
    def set(self, **kw):
        self.state.update(kw)

    def push_log(self, line: str):
        self.logs.append(line)

    def push_order(self, kind: str, order_id, stars=None, user=None):
        self.recent.appendleft((time.strftime("%H:%M:%S"), kind, str(order_id), stars, user))

    # --- рендер ---
    def _status_table(self) -> Table:
        t = Table.grid(padding=(0, 1))
        t.add_column(justify="right", style="grey62")
        t.add_column()
        s = self.state
        fp = Text()
        fp.append_text(_dot(bool(s.get("funpay_online"))))
        fp.append(self.funpay_name or "—", style="bold")
        t.add_row("FunPay", fp)
        ton, usdt = s.get("ton"), s.get("usdt")
        bal = Text()
        bal.append(f"{ton:.4f} TON" if isinstance(ton, (int, float)) else "—", style="bold #22d3ee")
        if isinstance(usdt, (int, float)):
            bal.append(f"  /  {usdt:.2f} USDT", style="#a78bfa")
        t.add_row("Кошелёк", bal)
        mode = Text("DRY-RUN", style="bold yellow3") if s.get("dry_run") else Text("LIVE", style="bold green3")
        if s.get("paused"):
            mode = Text("ПАУЗА", style="bold red3")
        t.add_row("Режим", mode)
        return t

    def _orders_panel(self) -> Panel:
        c = self.ledger.counts() if self.ledger else {}
        line = Text(justify="center")
        for key, lbl, style in (("AWAITING_NICK", "ник", "grey70"),
                                ("AWAITING_CONFIRMATION", "подтв", "grey70"),
                                ("DELIVERED", "выдано", "bold green3"),
                                ("NEEDS_REVIEW", "ревью", "bold yellow3"),
                                ("REFUNDED", "возврат", "red3")):
            line.append(f"  {lbl}:", style="grey50")
            line.append(f"{c.get(key, 0)}", style=style)
        return Panel(Align.center(line), title="реестр", box=box.ROUNDED, border_style="grey37")

    def _recent_panel(self) -> Panel:
        t = Table.grid(padding=(0, 1))
        for col in ("t", "kind", "id", "stars", "user"):
            t.add_column()
        colors = {"DELIVERED": "green3", "NEW": "cyan", "REVIEW": "yellow3", "REFUND": "red3"}
        if not self.recent:
            t.add_row(Text("— пока пусто —", style="grey42"))
        for ts, kind, oid, stars, user in self.recent:
            t.add_row(Text(ts, style="grey50"),
                      Text(kind, style=colors.get(kind, "white")),
                      Text(f"#{oid}", style="grey70"),
                      Text(f"{stars}★" if stars else "", style="magenta"),
                      Text(f"@{user}" if user else "", style="cyan"))
        return Panel(t, title="последние заказы", box=box.ROUNDED, border_style="grey37")

    def _log_panel(self) -> Panel:
        body = Text("\n".join(self.logs) if self.logs else "…", style="grey70")
        return Panel(body, title="лог", box=box.ROUNDED, border_style="grey30")

    def render(self) -> Group:
        header = Panel(
            Align.center(Group(
                Text(_brand_title(self.funpay_name), style="bold #22d3ee", justify="center"),
                _credit_line(),
            )),
            box=box.HEAVY, border_style="#22d3ee", padding=(0, 2),
        )
        status = Panel(self._status_table(), title="статус", box=box.ROUNDED, border_style="grey37")
        return Group(header, self._orders_panel(), status,
                     self._recent_panel(), self._log_panel())

    # --- живой цикл ---
    def start(self, console: Console | None = None, refresh: float = 2.0):
        from rich.live import Live
        console = console or Console()
        self._live = Live(self.render(), console=console, refresh_per_second=4, screen=False)
        self._live.start()

        def _loop():
            while not self._stop.wait(refresh):
                try:
                    self._live.update(self.render())
                except Exception:
                    pass
        self._thread = threading.Thread(target=_loop, name="dashboard", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._live:
            try:
                self._live.stop()
            except Exception:
                pass
