"""
bot_fragment.py — бот автопродажи Telegram Stars на FunPay через Fragment (self-hosted).

Денежно-безопасная версия с эталонными паттернами:
- self-hosted Fragment (seed локально), категории ошибок -> реакции;
- идемпотентный реестр заказов (ledger.py): звёзды уходят 1 раз, переживает рестарт;
- кол-во звёзд и @username из параметров заказа FunPay (lot_params/buyer_params),
  с быстрым путём выдачи, когда ник собран на чекауте;
- гард author_id==0, дедуп сообщений, состояние по buyer_id;
- per-chat пейсер, Telegram-алерты, статистика, бонус за отзыв;
- анимированный Rich-дашборд.

Проект: ProdX (https://prodx.pro)
Разработчик: Xuisuki — Telegram @Xuisuki, https://github.com/Xuisuki
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import config
import stars_logic as sl
import fragment_stars as fs
import alerts
import stats
import rewards
import dashboard as dash
from pacer import Pacer
from ledger import OrderLedger, DELIVERING, NEEDS_REVIEW

from FunPayAPI import Account
from FunPayAPI.updater.runner import Runner
from FunPayAPI.updater.events import NewOrderEvent, NewMessageEvent, OrderStatusChangedEvent

logger = logging.getLogger("StarsBot")

# ============ ЛОГИ ============
_LOG_FMT = "%(asctime)s [%(levelname)s] %(name)s | %(message)s"


class _PlainFile(logging.Formatter):
    def format(self, record):
        return sl.strip_ansi(super().format(record))


class _DashHandler(logging.Handler):
    """Прокидывает лог-строки в панель дашборда."""
    def __init__(self, board):
        super().__init__()
        self.board = board

    def emit(self, record):
        try:
            self.board.push_log(sl.strip_ansi(self.format(record)))
        except Exception:
            pass


def setup_logging(board=None, to_console=True):
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    fileh = logging.FileHandler("log.txt", encoding="utf-8")
    fileh.setFormatter(_PlainFile(_LOG_FMT))
    root.addHandler(fileh)

    if board is not None:
        dh = _DashHandler(board)
        dh.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))
        root.addHandler(dh)
    if to_console:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter(_LOG_FMT))
        root.addHandler(ch)

    audit = logging.getLogger("money_audit")
    audit.setLevel(logging.INFO)
    audit.handlers.clear()
    ah = logging.FileHandler("money_audit.log", encoding="utf-8")
    ah.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    audit.addHandler(ah)
    audit.propagate = False
    return audit


audit_logger = logging.getLogger("money_audit")

# ============ КОНТЕКСТ ============


@dataclass
class Ctx:
    account: Account
    ledger: OrderLedger
    pacer: Pacer
    board: "dash.Dashboard"
    executor: ThreadPoolExecutor


def say(ctx: Ctx, chat_id, text: str):
    """Отправить сообщение покупателю через пейсер (человеческая задержка по чату)."""
    ctx.pacer.say(chat_id, text)


# ============ FunPay helpers ============
def get_subcategory_id_safe(order, account):
    subcat = getattr(order, "subcategory", None)
    if subcat and hasattr(subcat, "id"):
        return subcat.id
    try:
        full = account.get_order(order.id)
        subcat = getattr(full, "subcategory", None)
        if subcat and hasattr(subcat, "id"):
            return subcat.id
    except Exception as e:
        logger.warning("не удалось загрузить заказ %s: %s", order.id, e)
    return None


def deactivate_category(account: Account, category_id: int) -> int:
    """Канонная деактивация лотов: get_my_subcategory_lots -> get_lot_fields -> active=False -> save_lot."""
    try:
        lots = account.get_my_subcategory_lots(category_id)
    except Exception as e:
        logger.error("[LOTS] не получить лоты категории %s: %s", category_id, e)
        return 0
    n = 0
    for lot in lots or []:
        lot_id = getattr(lot, "id", None) or (lot.get("id") if isinstance(lot, dict) else None)
        if not lot_id:
            continue
        try:
            fields = account.get_lot_fields(lot_id)
            if not getattr(fields, "active", True):
                continue
            fields.active = False
            account.save_lot(fields)
            n += 1
            logger.info("[LOTS] деактивирован лот %s", lot_id)
        except Exception as e:
            logger.error("[LOTS] не деактивировать лот %s: %s", lot_id, e)
    logger.warning("[LOTS] деактивировано: %s", n)
    return n


# ============ ЯДРО ВЫДАЧИ ============
def deliver(ctx: Ctx, order_id, chat_id, buyer_id, username: str, stars: int):
    """Выдать звёзды. Идемпотентно: реальная отправка не повторится для одного заказа."""
    ledger = ctx.ledger
    if not ledger.try_begin_delivery(order_id):
        logger.info("заказ %s уже выдаётся/выдан — пропуск", order_id)
        return

    bonus = rewards.peek(buyer_id)
    total = int(stars) + int(bonus or 0)
    say(ctx, chat_id, f"Отправляю {total} звёзд пользователю @{username}...")

    res = fs.buy_stars(username, total)
    cat = res.category
    logger.info("[SEND] order=%s @%s stars=%s ok=%s cat=%s tx=%s",
                order_id, username, total, res.ok, cat, res.transaction_id)

    if res.ok:
        ledger.mark_delivered(order_id, username, total, detail={"tx": res.transaction_id})
        stats.delivered(total, cost_usdt=(total / 50.0) * config.COST_USDT_PER_50)
        rewards.record_delivery(order_id, buyer_id)
        if bonus:
            rewards.consume(buyer_id)
        ctx.board.push_order("DELIVERED", order_id, total, username)
        audit_logger.info("DELIVERED order=%s @%s stars=%s tx=%s", order_id, username, total, res.transaction_id)
        say(ctx, chat_id, f"Готово! Отправлено {total} звёзд пользователю @{username}."
                          + (f" TX: {res.transaction_id}" if res.transaction_id and res.transaction_id != 'DRYRUN' else ""))
        say(ctx, chat_id, "Пожалуйста, подтвердите выполнение заказа и оставьте отзыв — это помогает!\n"
                          f"https://funpay.com/orders/{order_id}/")
        return

    # --- провал: реакция по категории ---
    stats.failed(cat)
    audit_logger.info("FAIL order=%s @%s stars=%s cat=%s msg=%s", order_id, username, total, cat, res.message[:200])
    logger.error("[SEND-FAIL] order=%s cat=%s: %s", order_id, cat, res.message[:300])

    if cat == "bad_username":
        # отправки не было -> не возврат, а переспрос корректного ника.
        ledger.require_new_nick(order_id, res.message)
        say(ctx, chat_id, f'Пользователь @{username} не найден в Telegram/Fragment. '
                          'Пришлите, пожалуйста, корректный тег в формате @username.')
        return

    if cat == "low_balance":
        ledger.mark_failed(order_id, res.message)
        alerts.send(f"[{config.brand()}] НИЗКИЙ БАЛАНС Fragment — заказ {order_id} не выдан. Пополните кошелёк.")
        if config.AUTO_DEACTIVATE:
            deactivate_category(ctx.account, config.DEACTIVATE_CATEGORY_ID)
        if config.AUTO_REFUND_ON_FAIL:
            _refund(ctx, order_id, chat_id, "низкий баланс Fragment")
        else:
            say(ctx, chat_id, "Временная техническая пауза выдачи. Оператор свяжется с вами.")
        return

    if cat in ("cookies", "kyc", "config"):
        # системная проблема: выдача остановлена, звёзд не ушло, но нужен оператор.
        ledger.mark_needs_review(order_id, f"{cat}: {res.message}")
        alerts.send(f"[{config.brand()}] ВЫДАЧА ОСТАНОВЛЕНА ({cat}) — заказ {order_id}. Требуется вмешательство.")
        say(ctx, chat_id, "Заказ принят, идёт обработка. Оператор подключится в ближайшее время.")
        return

    # tx_failed / other -> неоднозначно (звёзды могли уйти) -> ручная проверка, БЕЗ авто-возврата.
    ledger.mark_needs_review(order_id, f"{cat}: {res.message}")
    alerts.send(f"[{config.brand()}] НУЖНА ПРОВЕРКА — заказ {order_id} ({cat}): звёзды могли уйти. Проверьте вручную.")
    say(ctx, chat_id, "Заказ принят в обработку. Из-за технической ошибки выдача проверяется вручную "
                      "(до ~15 минут). Средства повторно не списаны.")


def _refund(ctx: Ctx, order_id, chat_id, reason: str) -> bool:
    try:
        ctx.account.refund(order_id)
        ctx.ledger.mark_refunded(order_id, reason)
        stats.refunded()
        audit_logger.info("REFUNDED order=%s reason=%s", order_id, reason)
        say(ctx, chat_id, "Средства возвращены.")
        return True
    except Exception as e:
        logger.error("возврат заказа %s не удался: %s", order_id, e)
        say(ctx, chat_id, "Ошибка возврата. Свяжитесь с админом.")
        return False


# ============ ОБРАБОТЧИКИ ============
def resolve_order(order):
    lot_params = getattr(order, "lot_params", None)
    buyer_params = getattr(order, "buyer_params", None)
    title = getattr(order, "title", "") or getattr(order, "short_description", "") or ""
    desc = getattr(order, "full_description", "") or ""
    amount = getattr(order, "amount", None)
    return sl.resolve_order(lot_params, buyer_params, title, desc, amount,
                            multiply_by_amount=config.STARS_MULTIPLY_BY_AMOUNT)


def handle_order(ctx: Ctx, event):
    subcat_id = get_subcategory_id_safe(event.order, ctx.account)
    if subcat_id != config.STARS_SUBCATEGORY_ID:
        logger.info("пропуск заказа — подкатегория %s (ждём %s)", subcat_id, config.STARS_SUBCATEGORY_ID)
        return

    order = ctx.account.get_order(event.order.id)
    stars, username, reason = resolve_order(order)

    if not ctx.ledger.create_order(order.id, order.buyer_id, order.chat_id, stars):
        logger.info("заказ %s уже в реестре — пропуск повтора", order.id)
        return

    stats.order()
    ctx.board.push_order("NEW", order.id, stars, username)
    logger.info("новый заказ #%s | звёзд: %s | ник: %s | %s", order.id, stars, username, reason)

    if stars is None:
        ctx.ledger.mark_needs_review(order.id, "не определено количество звёзд")
        alerts.send(f"[{config.brand()}] Заказ {order.id}: не удалось определить количество звёзд. Проверьте вручную.")
        say(ctx, order.chat_id, "Спасибо за покупку! Заказ принят в ручную обработку — оператор свяжется с вами.")
        return

    if username:
        # Быстрый путь: ник собран на чекауте FunPay -> выдаём сразу, без вопросов.
        ctx.ledger.set_awaiting_confirmation(order.id, username)
        say(ctx, order.chat_id, f"Спасибо за покупку! Выдаю {stars} звёзд на @{username}...")
        ctx.executor.submit(_safe_deliver, ctx, order.id, order.chat_id, order.buyer_id, username, stars)
        return

    # Ник не собран -> просим в чате.
    say(ctx, order.chat_id,
        f"Спасибо за покупку!\n\nК выдаче: {stars} звёзд\n\n"
        "Пришлите ваш Telegram-тег в формате @username.\n"
        "Если не знаете тег: профиль Telegram -> «Имя пользователя».")


def _safe_deliver(ctx: Ctx, order_id, chat_id, buyer_id, username, stars):
    try:
        deliver(ctx, order_id, chat_id, buyer_id, username, stars)
    except Exception:
        logger.exception("deliver упал для заказа %s", order_id)
        ctx.ledger.mark_needs_review(order_id, "исключение в deliver")


def _accept_nick_or_ask(ctx: Ctx, order_id, chat_id, text: str):
    """Валидный тег -> ждём подтверждения; иначе просим корректный. (Fragment проверит существование при выдаче.)"""
    if sl.is_valid_nick(text):
        ctx.ledger.set_awaiting_confirmation(order_id, sl.normalize_username(text))
        say(ctx, chat_id, f"Вы указали: {text}.\nЕсли верно — отправьте +.\n"
                          "Если нужно изменить — пришлите другой тег в формате @username.")
    else:
        say(ctx, chat_id, f'Тег "{text}" не похож на @username. Пришлите в формате @username (пример: @durov).')


def handle_message(ctx: Ctx, event, seen: set):
    msg = event.message
    chat_id, user_id = msg.chat_id, msg.author_id
    text = (msg.text or "").strip()

    if user_id == ctx.account.id:
        return
    if not user_id:                       # системные уведомления FunPay (author_id=0)
        return
    mid = getattr(msg, "id", None)
    if mid is not None:
        if mid in seen:
            return
        seen.add(mid)
        if len(seen) > 5000:
            seen.clear()

    order = ctx.ledger.get_active_by_buyer(user_id)
    if not order:
        return
    order_id = order["order_id"]

    if order["state"] == "AWAITING_NICK":
        _accept_nick_or_ask(ctx, order_id, chat_id, text)

    elif order["state"] == "AWAITING_CONFIRMATION":
        if text in ("+", "＋", "да", "yes", "ok", "ок"):
            stars, username = order["stars"], order["username"]
            if stars is None:
                ctx.ledger.mark_needs_review(order_id, "нет количества звёзд")
                say(ctx, chat_id, "Заказ в ручной обработке. Оператор свяжется с вами.")
                return
            if config.PREFLIGHT_BALANCE and not config.DRY_RUN:
                bal = fs.get_ton_balance()
                if bal is not None and bal < config.FRAGMENT_MIN_BALANCE:
                    ctx.ledger.mark_failed(order_id, f"низкий баланс TON {bal}")
                    alerts.send(f"[{config.brand()}] Низкий баланс TON ({bal}) — заказ {order_id} отложен.")
                    say(ctx, chat_id, "Временная техническая пауза. Оператор свяжется с вами.")
                    return
            ctx.executor.submit(_safe_deliver, ctx, order_id, chat_id, order["buyer_id"], username, stars)
        else:
            _accept_nick_or_ask(ctx, order_id, chat_id, text)


def handle_status(ctx: Ctx, event):
    """Ловим появление отзыва -> начисляем бонус к следующему заказу."""
    try:
        oid = event.order.id
        _check_review(ctx, oid)
    except Exception as e:
        logger.debug("handle_status: %s", e)


def _check_review(ctx: Ctx, oid):
    if rewards.already_rewarded(oid):
        return
    buyer = rewards.buyer_of(oid)
    if buyer is None:
        return
    try:
        order = ctx.account.get_order(oid)
    except Exception:
        return
    if getattr(order, "review", None):
        rewards.add_rewarded(oid)
        rewards.grant(buyer, config.REVIEW_BONUS_STARS)
        logger.info("бонус +%s звёзд начислен покупателю %s за отзыв по %s",
                    config.REVIEW_BONUS_STARS, buyer, oid)


# ============ ФОНОВЫЕ ПОТОКИ ============
def review_sweep(ctx: Ctx):
    while True:
        time.sleep(config.REVIEW_SWEEP_INTERVAL)
        for oid in rewards.unrewarded_delivered():
            _check_review(ctx, oid)


def balance_monitor(ctx: Ctx):
    warned = {"tier": "ok"}
    while True:
        try:
            ton = fs.get_ton_balance()
            ctx.board.set(ton=ton)
            if ton is not None:
                if ton < config.BALANCE_CRIT_TON and warned["tier"] != "crit":
                    warned["tier"] = "crit"
                    alerts.send(f"[{config.brand()}] КРИТ: баланс TON {ton:.4f} < {config.BALANCE_CRIT_TON}. Выдача под угрозой.")
                    if config.AUTO_DEACTIVATE:
                        deactivate_category(ctx.account, config.DEACTIVATE_CATEGORY_ID)
                elif ton < config.BALANCE_WARN_TON and warned["tier"] == "ok":
                    warned["tier"] = "warn"
                    alerts.send(f"[{config.brand()}] Внимание: баланс TON {ton:.4f} < {config.BALANCE_WARN_TON}.")
                elif ton >= config.BALANCE_WARN_TON:
                    warned["tier"] = "ok"
        except Exception as e:
            logger.debug("balance_monitor: %s", e)
        time.sleep(config.BALANCE_CHECK_INTERVAL)


def make_command_handler(ctx: Ctx):
    def handler(text: str, chat_id):
        cmd = text.lower().lstrip("/").split()[0] if text.strip() else ""
        if cmd in ("stats", "статистика", "стата"):
            w = fs.get_wallet_info()
            alerts.send_to(chat_id, stats.report(w, config.COST_USDT_PER_50, config.USDT_RUB))
        elif cmd in ("balance", "баланс"):
            alerts.send_to(chat_id, f"TON: {fs.get_ton_balance()}")
        elif cmd in ("review", "ревью"):
            rows = ctx.ledger.list_by_state(NEEDS_REVIEW, limit=20)
            if not rows:
                alerts.send_to(chat_id, "NEEDS_REVIEW: пусто.")
            else:
                alerts.send_to(chat_id, "На проверке:\n" + "\n".join(
                    f"#{r['order_id']} {r.get('stars')}★ @{r.get('username')} — {r.get('last_error','')[:60]}" for r in rows))
        elif cmd in ("pause", "пауза"):
            ctx.board.set(paused=True)
            alerts.send_to(chat_id, "Пауза. Автовыдача остановлена оператором.")
        elif cmd in ("resume", "старт"):
            ctx.board.set(paused=False)
            alerts.send_to(chat_id, "Возобновлено.")
        else:
            alerts.send_to(chat_id, "Команды: /stats /balance /review /pause /resume")
    return handler


# ============ MAIN ============
def main():
    problems = config.validate()
    if not config.FUNPAY_AUTH_TOKEN:
        print("FUNPAY_AUTH_TOKEN не задан в .env"); return

    account = (Account(config.FUNPAY_AUTH_TOKEN, config.FUNPAY_USER_AGENT)
               if config.FUNPAY_USER_AGENT else Account(config.FUNPAY_AUTH_TOKEN))
    account.get()
    funpay_name = getattr(account, "username", None)
    # Бренд: .env BRAND_NAME -> имя FunPay-аккаунта -> "STARS BOT". Резолвим ОДИН раз,
    # чтобы баннер, дашборд, алерты и /stats показывали одно имя.
    if not config.BRAND_NAME and funpay_name:
        config.BRAND_NAME = funpay_name

    use_dash = sys.stdout.isatty()
    board = dash.Dashboard(ledger=None, funpay_name=funpay_name)
    setup_logging(board=board, to_console=not use_dash)

    for p in problems:
        logger.warning("config: %s", p)

    ledger = OrderLedger(config.LEDGER_DB)
    board.ledger = ledger
    # Реконсиляция: зависшее в DELIVERING после рестарта -> на ручную проверку.
    for o in ledger.list_by_state(DELIVERING):
        ledger.mark_needs_review(o["order_id"], "зависло в DELIVERING после рестарта")
        logger.warning("[RECONCILE] %s -> NEEDS_REVIEW", o["order_id"])

    pacer = Pacer(lambda cid, txt: _safe_send(account, cid, txt), config)
    pacer.start()
    executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="deliver")
    ctx = Ctx(account=account, ledger=ledger, pacer=pacer, board=board, executor=executor)

    board.set(funpay_online=True, dry_run=config.DRY_RUN)

    if use_dash:
        dash.animate_intro(funpay_name)
        board.start()
    else:
        logger.info("=== %s | by %s (%s) | dev %s ===", config.brand(), config.CREATOR, config.CREATOR_URL, config.DEV_TELEGRAM)

    logger.info("авторизован как %s | подкатегория %s | DRY_RUN=%s | движок Fragment=self-hosted",
                funpay_name, config.STARS_SUBCATEGORY_ID, config.DRY_RUN)

    stats.mark_start()
    threading.Thread(target=alerts.poll_commands, args=(make_command_handler(ctx),), daemon=True).start()
    threading.Thread(target=balance_monitor, args=(ctx,), daemon=True).start()
    threading.Thread(target=review_sweep, args=(ctx,), daemon=True).start()
    alerts.send(f"[{config.brand()}] Бот запущен ({'DRY-RUN' if config.DRY_RUN else 'LIVE'}). FunPay: {funpay_name}.")

    seen: set = set()
    runner = Runner(account)
    while True:
        try:
            for event in runner.listen(requests_delay=3.0):
                if getattr(board, "state", {}).get("paused"):
                    continue
                try:
                    if isinstance(event, NewOrderEvent):
                        handle_order(ctx, event)
                    elif isinstance(event, NewMessageEvent):
                        handle_message(ctx, event, seen)
                    elif isinstance(event, OrderStatusChangedEvent):
                        handle_status(ctx, event)
                except Exception:
                    logger.exception("ошибка обработки события")
        except Exception as e:
            logger.error("runner упал: %s — перезапуск через 10с", e)
            time.sleep(10)


def _safe_send(account, chat_id, text):
    try:
        account.send_message(chat_id, text)
    except Exception as e:
        logger.error("send_message в %s не удалось: %s", chat_id, e)


if __name__ == "__main__":
    main()
