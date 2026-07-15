"""
config.py — единый источник конфигурации Funpay-Telegram-Stars.

Все переменные читаются из .env (см. .env.example). Заполнить проще мастером:
    python first_start.py

Проект: ProdX (https://prodx.pro)
Разработчики: Xuisuki (@Xuisuki, github.com/Xuisuki) + mawlikow (@mawlikow, github.com/mawlikow)
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- кредиты (фиксированные, не редактируются оператором) ---
CREATOR = "ProdX"
CREATOR_URL = "https://prodx.pro"
DEV_TELEGRAM = "@Xuisuki"
DEV_GITHUB = "https://github.com/Xuisuki"
DEV2_TELEGRAM = "@mawlikow"
DEV2_GITHUB = "https://github.com/mawlikow"


def _b(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on", "да")


def _i(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, "")).strip())
    except (ValueError, AttributeError):
        return default


def _f(name: str, default: float) -> float:
    try:
        return float(str(os.getenv(name, "")).strip().replace(",", "."))
    except (ValueError, AttributeError):
        return default


# ---- бренд оператора (меняется под пользователя; в баннере терминала) ----
BRAND_NAME = os.getenv("BRAND_NAME", "").strip()          # пусто -> имя FunPay-аккаунта / "STARS BOT"
BRAND_TAGLINE = os.getenv("BRAND_TAGLINE", "").strip()

# ---- FunPay ----
FUNPAY_AUTH_TOKEN = os.getenv("FUNPAY_AUTH_TOKEN", "").strip()
FUNPAY_USER_AGENT = os.getenv("FUNPAY_USER_AGENT", "").strip() or None
STARS_SUBCATEGORY_ID = _i("STARS_SUBCATEGORY_ID", 2418)   # подкатегория с заказами Stars
DEACTIVATE_CATEGORY_ID = _i("DEACTIVATE_CATEGORY_ID", STARS_SUBCATEGORY_ID)

# ---- Fragment (self-hosted, вендорная PyFragment; seed остаётся ЛОКАЛЬНО) ----
FRAGMENT_SEED = os.getenv("FRAGMENT_SEED", "").strip()
TON_API_KEY = os.getenv("TON_API_KEY", "").strip()
FRAGMENT_COOKIES = os.getenv("FRAGMENT_COOKIES", "").strip()
FRAGMENT_WALLET_VERSION = os.getenv("FRAGMENT_WALLET_VERSION", "V5R1").strip()
FRAGMENT_PAYMENT_METHOD = os.getenv("FRAGMENT_PAYMENT_METHOD", "ton").strip()  # ton дешевле по газу
FRAGMENT_SHOW_SENDER = _b("FRAGMENT_SHOW_SENDER", False)
FRAGMENT_MIN_BALANCE = _f("FRAGMENT_MIN_BALANCE", 1.0)     # мин. баланс TON для выдачи

# ---- поведение выдачи ----
DRY_RUN = _b("DRY_RUN", True)                             # по умолчанию БЕЗОПАСНО: без реальной отправки
STARS_MULTIPLY_BY_AMOUNT = _b("STARS_MULTIPLY_BY_AMOUNT", True)
PREFLIGHT_BALANCE = _b("PREFLIGHT_BALANCE", True)
AUTO_REFUND_ON_FAIL = _b("AUTO_REFUND_ON_FAIL", False)    # возвраты по умолчанию делает оператор
AUTO_DEACTIVATE = _b("AUTO_DEACTIVATE", True)
LEDGER_DB = os.getenv("LEDGER_DB", "orders.db").strip()

# ---- пейсер человеческих задержек (ПО ЧАТУ, не глобально) ----
# interval(n) = clamp(MIN, MAX, PER_ORDER*n - OFFSET); n = сообщений в очереди ЭТОГО чата.
REPLY_DELAY_MIN = _i("REPLY_DELAY_MIN", 15)
REPLY_DELAY_PER_ORDER = _f("REPLY_DELAY_PER_ORDER", 18.0)
REPLY_DELAY_OFFSET = _f("REPLY_DELAY_OFFSET", 30.0)
REPLY_DELAY_MAX = _i("REPLY_DELAY_MAX", 600)
REPLY_JITTER = _f("REPLY_JITTER", 0.15)
PACER_ENABLED = _b("PACER_ENABLED", True)

# ---- экономика/статистика ----
COST_USDT_PER_50 = _f("COST_USDT_PER_50", 0.75)
USDT_RUB = _f("USDT_RUB", 72.0)

# ---- проактивный мониторинг баланса ----
BALANCE_CHECK_INTERVAL = _i("BALANCE_CHECK_INTERVAL", 600)
BALANCE_WARN_TON = _f("BALANCE_WARN_TON", 0.5)
BALANCE_CRIT_TON = _f("BALANCE_CRIT_TON", 0.1)

# ---- Telegram-алерты оператору (отдельный bot-токен от @BotFather) ----
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_ADMIN_IDS = [
    int(x) for x in os.getenv("TELEGRAM_ADMIN_IDS", "").replace(" ", "").split(",") if x.strip().isdigit()
]

# ---- бонус за отзыв: +N звёзд к следующему заказу ----
REVIEW_BONUS_STARS = _i("REVIEW_BONUS_STARS", 1)
REVIEW_SWEEP_INTERVAL = _i("REVIEW_SWEEP_INTERVAL", 1200)


def brand() -> str:
    """Имя бренда для баннера (fallback подставит имя FunPay-аккаунта в рантайме)."""
    return BRAND_NAME or "STARS BOT"


def validate() -> list[str]:
    """Список проблем конфигурации (пустой = всё ок)."""
    problems = []
    if not FUNPAY_AUTH_TOKEN:
        problems.append("FUNPAY_AUTH_TOKEN не задан")
    if not DRY_RUN:
        if not FRAGMENT_SEED:
            problems.append("FRAGMENT_SEED не задан (нужен для боевого режима)")
        if not TON_API_KEY:
            problems.append("TON_API_KEY не задан (tonconsole.com)")
        if not FRAGMENT_COOKIES:
            problems.append("FRAGMENT_COOKIES не заданы (stel_*)")
    if REPLY_DELAY_MIN > REPLY_DELAY_MAX:
        problems.append("REPLY_DELAY_MIN > REPLY_DELAY_MAX")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_IDS:
        problems.append("Telegram-алерты не настроены (TELEGRAM_BOT_TOKEN/ADMIN_IDS)")
    return problems
