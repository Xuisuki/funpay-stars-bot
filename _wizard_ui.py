# -*- coding: utf-8 -*-
"""
_wizard_ui.py — общий UI-тулкит установщика (Rich).

Кастомный терминал в едином «ионном» стиле проекта (cyan -> purple):
анимированный баннер с градиентной волной, панели-карточки полей с подсказкой
«что это / где взять», маскируемый ввод секретов, валидация, сводка и финал.

Один и тот же файл живёт в обоих проектах (reporadar / funpay-stars-bot),
чтобы установщики выглядели одинаково.

Проект: ProdX (https://prodx.pro)
Разработчики: @Xuisuki + @mawlikow (github.com/Xuisuki, github.com/mawlikow)
"""
from __future__ import annotations

import sys
import time

try:
    from rich.align import Align
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.prompt import Confirm, Prompt
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text
    from rich import box
except ImportError:
    sys.stderr.write(
        "\n  Мастеру настройки нужен пакет rich.\n"
        "  Запустите установщик: ./install.sh   (Windows: install.ps1)\n"
        "  Либо вручную:         pip install rich colorama\n\n")
    raise SystemExit(1)

# --- фирменные значения (фиксированные, не редактируются оператором) ---
CREATOR = "ProdX"
CREATOR_URL = "https://prodx.pro"
DEVS = "@Xuisuki · @mawlikow"

# «Ионная» палитра градиентной волны (как в дашборде).
GRADIENT = ["#38bdf8", "#22d3ee", "#67e8f9", "#a5f3fc", "#c4b5fd", "#a78bfa", "#818cf8"]
CYAN = "#22d3ee"
PURPLE = "#a78bfa"
DIM = "#3b4252"

console = Console()
_TTY = bool(getattr(sys.stdout, "isatty", lambda: False)())


# ---------------------------------------------------------------- баннер
def credit_line() -> Text:
    t = Text(justify="center")
    t.append("by ", style="grey50")
    t.append(CREATOR, style=f"bold {PURPLE}")
    t.append(f" · {CREATOR_URL}", style="#818cf8")
    t.append("   |   dev ", style="grey50")
    t.append(DEVS, style=f"bold {CYAN}")
    return t


def _banner_panel(title: str, subtitle: str, phase: float) -> Panel:
    spaced = "  ".join(title.upper())
    text = Text(justify="center")
    n = max(1, len(spaced))
    head = int(phase * (n + 6)) - 3
    for i, ch in enumerate(spaced):
        dist = abs(i - head)
        if dist <= 3:
            text.append(ch, style=f"bold {GRADIENT[min(dist, len(GRADIENT) - 1)]}")
        else:
            text.append(ch, style=f"bold {DIM}")
    sub = Text(subtitle, style="italic grey62", justify="center")
    tag = Text("У С Т А Н О В Щ И К", style="grey42", justify="center")
    return Panel(
        Align.center(Group(Text(""), text, Text(""), sub, tag, Text(""), credit_line())),
        box=box.DOUBLE, border_style=CYAN, padding=(1, 4),
    )


def intro(title: str, subtitle: str) -> None:
    """Анимированный интро-баннер (в не-tty — один финальный кадр)."""
    if not _TTY:
        console.print(_banner_panel(title, subtitle, 0.5))
        return
    from rich.live import Live
    frames = 26
    try:
        with Live(console=console, refresh_per_second=30, transient=False) as live:
            for f in range(frames + 6):
                live.update(_banner_panel(title, subtitle, f / frames))
                time.sleep(1.6 / frames)
    except Exception:
        console.print(_banner_panel(title, subtitle, 0.5))


def section(n: int, total: int, title: str) -> None:
    console.print()
    console.print(Rule(Text(f"  Шаг {n}/{total}   {title}  ", style=f"bold {CYAN}"),
                       style=DIM, align="center"))


# ---------------------------------------------------------------- поля
def _help_panel(title: str, whatis: str, where: list[str] | None, step: str) -> Panel:
    body = Text()
    body.append(whatis, style="grey78")
    if where:
        body.append("\n\nГде взять:\n", style=f"bold {PURPLE}")
        for i, line in enumerate(where, 1):
            body.append(f"  {i}. ", style=CYAN)
            body.append(line + ("\n" if i < len(where) else ""), style="grey70")
    return Panel(body, title=Text(f" {title} ", style=f"bold {CYAN}"),
                 subtitle=Text(step, style="grey42") if step else None,
                 title_align="left", subtitle_align="right", box=box.ROUNDED,
                 border_style="grey37", padding=(1, 2))


def _mask(s: str, head: int = 3, tail: int = 3) -> str:
    if not s:
        return "(пусто)"
    if len(s) <= head + tail:
        return "*" * len(s)
    return s[:head] + "*" * (len(s) - head - tail) + s[-tail:]


def ask_text(title, whatis, *, where=None, default="", required=False,
             secret=False, validate=None, step="") -> str:
    """Показать карточку-подсказку и запросить значение с валидацией."""
    console.print(_help_panel(title, whatis, where, step))
    while True:
        val = Prompt.ask(Text("  ввод", style=CYAN), default=default or "",
                         password=secret, show_default=bool(default) and not secret)
        val = (val or "").strip()
        if not val and required:
            console.print("  [red3]Это поле обязательно.[/]"); continue
        if val and validate:
            msg = validate(val)
            if msg:
                console.print(f"  [red3]{msg}[/]"); continue
        if val:
            console.print(f"  [green3]OK[/]  {_mask(val) if secret else val}")
        return val


def ask_bool(title, whatis, *, default=True, where=None, step="") -> bool:
    console.print(_help_panel(title, whatis, where, step))
    return Confirm.ask(Text("  выбор", style=CYAN), default=default)


def ask_choice(title, whatis, options: list[tuple[str, str]], *, default="", step="") -> str:
    """options = [(значение, описание)]. Возвращает выбранное значение."""
    body = Text()
    body.append(whatis + "\n", style="grey78")
    for val, desc in options:
        mark = "●" if val == default else "○"
        body.append(f"\n  {mark} ", style=CYAN)
        body.append(f"{val}", style=f"bold {PURPLE}")
        body.append(f"  — {desc}", style="grey70")
    console.print(Panel(body, title=Text(f" {title} ", style=f"bold {CYAN}"),
                        subtitle=Text(step, style="grey42") if step else None,
                        title_align="left", subtitle_align="right", box=box.ROUNDED,
                        border_style="grey37", padding=(1, 2)))
    return Prompt.ask(Text("  выбор", style=CYAN),
                      choices=[v for v, _ in options], default=default)


# ---------------------------------------------------------------- итоги
def summary(rows: list[tuple[str, str, bool]]) -> None:
    """rows = [(label, value, is_secret)]."""
    t = Table.grid(padding=(0, 2))
    t.add_column(justify="right", style="grey62")
    t.add_column()
    for label, value, sec in rows:
        if sec:
            t.add_row(label, Text(_mask(value), style=PURPLE))
        else:
            t.add_row(label, Text(value) if value else Text("(пусто)", style="grey42"))
    console.print(Panel(t, title=Text(" сводка настроек ", style=f"bold {CYAN}"),
                        title_align="left", box=box.ROUNDED, border_style=CYAN,
                        padding=(1, 2)))


def check(label: str, ok: bool | None, detail: str = "") -> None:
    """Строка live-проверки. ok=None — пропущено/неизвестно."""
    color = "green3" if ok else ("grey42" if ok is None else "red3")
    line = Text()
    line.append("  ● ", style=f"bold {color}")
    line.append(f"{label}  ", style="grey78")
    line.append(detail, style="grey54")
    console.print(line)


def success(title: str, run_cmd: str, extra_lines: list[str]) -> None:
    body = Text()
    body.append("Запуск:  ", style="grey62")
    body.append(run_cmd + "\n", style=f"bold {CYAN}")
    for ln in extra_lines:
        body.append("\n" + ln, style="grey74")
    console.print(Panel(Align.left(Group(
        Text(title, style="bold green3"), Text(""), body, Text(""), credit_line())),
        box=box.HEAVY, border_style="green3", padding=(1, 3)))


def note(msg: str) -> None:
    console.print(f"  [grey62]{msg}[/]")


def bye(msg: str) -> None:
    console.print(f"\n[yellow3]{msg}[/]")
