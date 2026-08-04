from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.db.models import Wallet
from bot.utils import format_amount


def wallet_picker(wallets: list[Wallet]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{w.address} ({format_amount(w.balance)} USDT)", callback_data=f"wallet:{w.id}"
            )
        ]
        for w in wallets
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def currency_picker() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="RUB", callback_data="currency:RUB"),
            InlineKeyboardButton(text="USD", callback_data="currency:USD"),
            InlineKeyboardButton(text="EUR", callback_data="currency:EUR"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def period_picker() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="Day", callback_data="period:day"),
            InlineKeyboardButton(text="Week", callback_data="period:week"),
            InlineKeyboardButton(text="Month", callback_data="period:month"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="Submit", callback_data="confirm"),
            InlineKeyboardButton(text="Cancel", callback_data="cancel"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Skip", callback_data="skip")]]
    )


def done_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Done", callback_data="done_photos")]]
    )


def request_card_keyboard(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Cancel", callback_data=f"req_cancel:{request_id}")],
            [InlineKeyboardButton(text="Attach a report", callback_data=f"req_attach:{request_id}")],
        ]
    )
