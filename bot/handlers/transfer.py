from decimal import Decimal

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.db.engine import get_session
from bot.keyboards.inline import confirm_keyboard, wallet_picker
from bot.keyboards.menus import CMD_TRANSFER_BETWEEN_WALLETS, TRANSFER_BETWEEN_WALLETS, executor_menu
from bot.services import wallets as wallet_service
from bot.services.notify import post_to_group
from bot.utils import esc, format_amount, parse_amount

router = Router()
router.message.filter(F.chat.type == "private")


class TransferStates(StatesGroup):
    choosing_wallet_from = State()
    choosing_wallet_to = State()
    entering_sum = State()
    confirming = State()


@router.message(F.text == TRANSFER_BETWEEN_WALLETS)
@router.message(Command(CMD_TRANSFER_BETWEEN_WALLETS))
async def start_transfer(message: Message, role: str | None, state: FSMContext) -> None:
    if role != "executor":
        return
    async with get_session() as session:
        available_wallets = await wallet_service.list_wallets(session)
    if len(available_wallets) < 2:
        await message.answer("You need at least two wallets to make a transfer.")
        return
    await state.set_state(TransferStates.choosing_wallet_from)
    await message.answer("Choose wallet from:", reply_markup=wallet_picker(available_wallets))


@router.callback_query(TransferStates.choosing_wallet_from, F.data.startswith("wallet:"))
async def choose_wallet_from(callback: CallbackQuery, state: FSMContext) -> None:
    wallet_id = int(callback.data.split(":", 1)[1])
    await state.update_data(wallet_from_id=wallet_id)
    await state.set_state(TransferStates.choosing_wallet_to)
    async with get_session() as session:
        available_wallets = await wallet_service.list_wallets(session)
    others = [w for w in available_wallets if w.id != wallet_id]
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Choose wallet to:", reply_markup=wallet_picker(others))
    await callback.answer()


@router.callback_query(TransferStates.choosing_wallet_to, F.data.startswith("wallet:"))
async def choose_wallet_to(callback: CallbackQuery, state: FSMContext) -> None:
    wallet_id = int(callback.data.split(":", 1)[1])
    data = await state.get_data()
    if wallet_id == data["wallet_from_id"]:
        await callback.answer("Choose a different wallet than wallet from.", show_alert=True)
        return
    await state.update_data(wallet_to_id=wallet_id)
    await state.set_state(TransferStates.entering_sum)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Sum:")
    await callback.answer()


@router.message(TransferStates.entering_sum)
async def enter_sum(message: Message, state: FSMContext) -> None:
    try:
        amount = parse_amount(message.text or "")
    except ValueError:
        await message.answer("Please enter a valid positive number for Sum.")
        return
    data = await state.update_data(sum=str(amount))
    async with get_session() as session:
        wallet_from = await wallet_service.get_wallet(session, data["wallet_from_id"])
        wallet_to = await wallet_service.get_wallet(session, data["wallet_to_id"])
    summary = (
        "<b>Transfer between wallets</b>\n"
        f"From: {esc(wallet_from.address)}\n"
        f"To: {esc(wallet_to.address)}\n"
        f"Sum: {format_amount(amount)} USDT"
    )
    await state.set_state(TransferStates.confirming)
    await message.answer(summary, reply_markup=confirm_keyboard())


@router.callback_query(TransferStates.confirming, F.data == "cancel")
async def cancel_transfer(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Canceled.", reply_markup=executor_menu())
    await callback.answer()


@router.callback_query(TransferStates.confirming, F.data == "confirm")
async def confirm_transfer(callback: CallbackQuery, state: FSMContext, bot: Bot, config: Config) -> None:
    data = await state.get_data()
    async with get_session() as session:
        try:
            wallet_from, wallet_to = await wallet_service.transfer_between_wallets(
                session, data["wallet_from_id"], data["wallet_to_id"], Decimal(data["sum"])
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
    await callback.message.answer("Transfer completed.", reply_markup=executor_menu())

    await post_to_group(
        bot,
        config,
        "<b>Transfer between wallets</b>\n"
        f"From: {esc(wallet_from.address)} (new balance: {format_amount(wallet_from.balance)} USDT)\n"
        f"To: {esc(wallet_to.address)} (new balance: {format_amount(wallet_to.balance)} USDT)\n"
        f"Sum: {format_amount(data['sum'])} USDT",
    )
    await callback.answer()
