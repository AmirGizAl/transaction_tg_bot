from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

NEW_TRANSACTION = "New transaction"
DOWNLOAD_REPORT = "Download report"
FIAT_TRANSACTION = "Fiat transaction"
ADD_WALLET = "Add wallet"
CHANGE_BALANCE = "Change balance"
TRANSFER_BETWEEN_WALLETS = "Tr. between wallets"

# Slash-command equivalents, registered in Telegram's "/" commands menu (bot/main.py) as a
# fallback entry point that doesn't depend on the reply keyboard being visible.
CMD_NEW_TRANSACTION = "new_transaction"
CMD_DOWNLOAD_REPORT = "download_report"
CMD_FIAT_TRANSACTION = "fiat_transaction"
CMD_ADD_WALLET = "add_wallet"
CMD_CHANGE_BALANCE = "change_balance"
CMD_TRANSFER_BETWEEN_WALLETS = "transfer_wallets"


def owner_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=NEW_TRANSACTION)],
            [KeyboardButton(text=DOWNLOAD_REPORT)],
        ],
        resize_keyboard=True,
        is_persistent=True,
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
        is_persistent=True,
    )
