import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from dotenv import load_dotenv

load_dotenv()

MAX_AMOUNT = Decimal("1000000000")


@dataclass(frozen=True)
class Currency:
    code: str
    display: str


CURRENCIES: dict[str, Currency] = {
    "star": Currency("Stars", "⭐ Telegram Stars"),
    "stars": Currency("Stars", "⭐ Telegram Stars"),
    "gram": Currency("TON", "TON"),
    "ton": Currency("TON", "TON"),
}


def parse_currency(raw: str) -> Currency:
    currency = CURRENCIES.get(raw.strip().lower())
    if currency is None:
        raise ValueError(
            "❌ Неизвестная валюта.\n\nДопустимые валюты: star (Telegram Stars) или gram (TON)."
        )
    return currency


def parse_amount(raw: str) -> str:
    """Validate a positive number and return it as a plain decimal string."""
    try:
        value = Decimal(raw.replace(",", "."))
    except (InvalidOperation, AttributeError):
        raise ValueError("❌ Сумма некорректна. Укажите положительное число, например 1400 или 10.")
    if not value.is_finite() or value <= 0 or value > MAX_AMOUNT:
        raise ValueError(
            "❌ Сумма некорректна. Она должна быть больше нуля и не превышать 1 000 000 000."
        )
    return format(value.normalize(), "f")


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_id: int | None
    database_path: str
    transfer_fee_text: str


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN не задан в переменных окружения.")

    admin_raw = os.getenv("ADMIN_ID", "").strip()
    admin_id = int(admin_raw) if admin_raw.isdigit() else 7323296973

    return Config(
        bot_token=token,
        admin_id=admin_id,
        database_path=os.getenv("DATABASE_PATH", "data/bot.sqlite3").strip(),
        transfer_fee_text=os.getenv(
            "TRANSFER_FEE_TEXT",
            "Если требуется 25 Telegram Stars, они должны быть на вашем балансе.",
        ).strip(),
    )
