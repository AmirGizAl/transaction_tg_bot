from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

NEW_TRANSACTION = "New transaction"
DOWNLOAD_REPORT = "Download report"
FIAT_TRANSACTION = "Fiat transaction"
ADD_WALLET = "Add wallet"
CHANGE_BALANCE = "Change balance"
TRANSFER_BETWEEN_WALLETS = "Tr. between wallets"


def owner_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=NEW_TRANSACTION)],
            [KeyboardButton(text=DOWNLOAD_REPORT)],
        ],
        resize_keyboard=True,
    )


def executor_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=FIAT_TRANSACTION)],
            [KeyboardButton(text=ADD_WALLET)],
            [KeyboardButton(text=CHANGE_BALANCE)],
            [KeyboardButton(text=TRANSFER_BETWEEN_WALLETS)],
            [KeyboardButton(text=DOWNLOAD_REPORT)],
        ],
        resize_keyboard=True,
    )
