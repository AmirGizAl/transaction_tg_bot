from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from html import escape as html_escape

from bot.config import MSK

TWO_PLACES = Decimal("0.01")


def to_msk(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(MSK)


def fmt_dt(dt: datetime) -> str:
    return to_msk(dt).strftime("%Y-%m-%d %H:%M:%S MSK")


def parse_amount(text: str, allow_zero: bool = False) -> Decimal:
    try:
        value = Decimal(text.strip().replace(",", ".")).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError("Invalid number") from exc
    if value < 0 or (not allow_zero and value == 0):
        raise ValueError("Amount must be positive")
    return value


def parse_signed_amount(text: str) -> Decimal:
    """Like parse_amount, but allows a leading '-' (e.g. for balance adjustments that
    can go either way). Zero is still rejected — it wouldn't be a meaningful change."""
    try:
        value = Decimal(text.strip().replace(",", ".")).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError("Invalid number") from exc
    if value == 0:
        raise ValueError("Amount must not be zero")
    return value


def format_amount(value) -> str:
    d = Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    sign = "-" if d < 0 else ""
    d = abs(d)
    int_part, frac_part = f"{d:,.2f}".split(".")
    int_part = int_part.replace(",", ".")
    return f"{sign}{int_part},{frac_part}"


def esc(text: str) -> str:
    return html_escape(str(text))
