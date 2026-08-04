from decimal import Decimal

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.db.engine import get_session
from bot.keyboards.inline import confirm_keyboard, skip_keyboard
from bot.keyboards.menus import ADD_WALLET, executor_menu
from bot.services import wallets as wallet_service
from bot.services.notify import post_to_group
from bot.utils import esc, format_amount, parse_amount

router = Router()
router.message.filter(F.chat.type == "private")


class AddWalletStates(StatesGroup):
    entering_address = State()
    entering_deposit = State()
    confirming = State()


@router.message(F.text == ADD_WALLET)
async def start_add_wallet(message: Message, role: str | None, state: FSMContext) -> None:
    if role != "executor":
        return
    await state.set_state(AddWalletStates.entering_address)
    await message.answer("Wallet address:")


@router.message(AddWalletStates.entering_address)
async def enter_address(message: Message, state: FSMContext) -> None:
    address = (message.text or "").strip()
    if not address:
        await message.answer("Please enter a wallet address.")
        return
    await state.update_data(address=address)
    await state.set_state(AddWalletStates.entering_deposit)
    await message.answer("Deposit (USDT), default 0. Send a number or press Skip.", reply_markup=skip_keyboard())


async def _show_wallet_summary(message: Message, state: FSMContext, deposit: Decimal) -> None:
    data = await state.update_data(deposit=str(deposit))
    summary = f"<b>New wallet</b>\nAddress: {esc(data['address'])}\nDeposit: {format_amount(deposit)} USDT"
    await state.set_state(AddWalletStates.confirming)
    await message.answer(summary, reply_markup=confirm_keyboard())


@router.callback_query(AddWalletStates.entering_deposit, F.data == "skip")
async def skip_deposit(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await _show_wallet_summary(callback.message, state, Decimal("0"))
    await callback.answer()


@router.message(AddWalletStates.entering_deposit)
async def enter_deposit(message: Message, state: FSMContext) -> None:
    try:
        deposit = parse_amount(message.text or "", allow_zero=True)
    except ValueError:
        await message.answer("Please enter a valid non-negative number, or press Skip.")
        return
    await _show_wallet_summary(message, state, deposit)


@router.callback_query(AddWalletStates.confirming, F.data == "cancel")
async def cancel_add_wallet(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Canceled.", reply_markup=executor_menu())
    await callback.answer()


@router.callback_query(AddWalletStates.confirming, F.data == "confirm")
async def confirm_add_wallet(callback: CallbackQuery, state: FSMContext, bot: Bot, config: Config) -> None:
    data = await state.get_data()
    async with get_session() as session:
        wallet = await wallet_service.add_wallet(session, data["address"], Decimal(data["deposit"]))

    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Wallet added.", reply_markup=executor_menu())

    await post_to_group(
        bot,
        config,
        f"<b>New wallet added</b>\nAddress: {esc(wallet.address)}\nDeposit: {format_amount(wallet.balance)} USDT",
    )
    await callback.answer()
