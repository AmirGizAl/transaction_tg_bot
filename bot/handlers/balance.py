from decimal import Decimal

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.db.engine import get_session
from bot.keyboards.inline import confirm_keyboard, wallet_picker
from bot.keyboards.menus import CHANGE_BALANCE, CMD_CHANGE_BALANCE, executor_menu
from bot.services import wallets as wallet_service
from bot.services.notify import post_to_group
from bot.utils import esc, format_amount, parse_signed_amount

router = Router()
router.message.filter(F.chat.type == "private")


class ChangeBalanceStates(StatesGroup):
    choosing_wallet = State()
    entering_sum = State()
    confirming = State()


def _signed_amount(amount) -> str:
    d = Decimal(str(amount))
    sign = "+" if d > 0 else ""
    return f"{sign}{format_amount(d)}"


@router.message(F.text == CHANGE_BALANCE)
@router.message(Command(CMD_CHANGE_BALANCE))
async def start_change_balance(message: Message, role: str | None, state: FSMContext) -> None:
    if role != "executor":
        return
    async with get_session() as session:
        available_wallets = await wallet_service.list_wallets(session)
    if not available_wallets:
        await message.answer("No wallets available yet. Add one first.")
        return
    await state.set_state(ChangeBalanceStates.choosing_wallet)
    await message.answer("Choose wallet:", reply_markup=wallet_picker(available_wallets))


@router.callback_query(ChangeBalanceStates.choosing_wallet, F.data.startswith("wallet:"))
async def choose_wallet(callback: CallbackQuery, state: FSMContext) -> None:
    wallet_id = int(callback.data.split(":", 1)[1])
    await state.update_data(wallet_id=wallet_id)
    await state.set_state(ChangeBalanceStates.entering_sum)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Sum: enter a positive number to add funds, or a negative one (e.g. -500) to subtract."
    )
    await callback.answer()


@router.message(ChangeBalanceStates.entering_sum)
async def enter_sum(message: Message, state: FSMContext) -> None:
    try:
        amount = parse_signed_amount(message.text or "")
    except ValueError:
        await message.answer("Please enter a valid non-zero number (e.g. 500 or -500).")
        return
    data = await state.update_data(change_sum=str(amount))
    async with get_session() as session:
        wallet = await wallet_service.get_wallet(session, data["wallet_id"])
    summary = (
        "<b>Change balance</b>\n"
        f"Wallet: {esc(wallet.address)}\n"
        f"Sum: {_signed_amount(amount)} USDT"
    )
    await state.set_state(ChangeBalanceStates.confirming)
    await message.answer(summary, reply_markup=confirm_keyboard())


@router.callback_query(ChangeBalanceStates.confirming, F.data == "cancel")
async def cancel_change_balance(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Canceled.", reply_markup=executor_menu())
    await callback.answer()


@router.callback_query(ChangeBalanceStates.confirming, F.data == "confirm")
async def confirm_change_balance(callback: CallbackQuery, state: FSMContext, bot: Bot, config: Config) -> None:
    data = await state.get_data()
    async with get_session() as session:
        try:
            wallet = await wallet_service.change_balance(
                session, data["wallet_id"], Decimal(data["change_sum"])
            )
        except wallet_service.InsufficientFundsError:
            await state.clear()
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer(
                "There are not enough funds on the wallet balance", reply_markup=executor_menu()
            )
            await callback.answer()
            return

    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Balance updated.", reply_markup=executor_menu())

    await post_to_group(
        bot,
        config,
        "<b>Balance changed</b>\n"
        f"Wallet: {esc(wallet.address)}\n"
        f"Sum: {_signed_amount(data['change_sum'])} USDT\n"
        f"New balance: {format_amount(wallet.balance)} USDT",
    )
    await callback.answer()
