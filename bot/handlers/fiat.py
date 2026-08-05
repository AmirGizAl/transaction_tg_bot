from decimal import Decimal

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.db.engine import get_session
from bot.db.models import Currency
from bot.keyboards.inline import confirm_keyboard, currency_picker, done_keyboard, wallet_picker
from bot.keyboards.menus import CMD_FIAT_TRANSACTION, FIAT_TRANSACTION, executor_menu
from bot.services import wallets as wallet_service
from bot.services.notify import post_photos_to_group
from bot.utils import esc, fmt_dt, format_amount, parse_amount

router = Router()
router.message.filter(F.chat.type == "private")


class FiatTransactionStates(StatesGroup):
    choosing_wallet = State()
    entering_sum = State()
    entering_received = State()
    choosing_currency = State()
    attaching_report = State()
    confirming = State()


def _fiat_summary_text(wallet_address: str, sum_usdt, amount_received, currency: str, photo_count: int) -> str:
    text = (
        "<b>Fiat transaction</b>\n"
        f"Wallet: {esc(wallet_address)}\n"
        f"Sum (USDT): {format_amount(sum_usdt)}\n"
        f"Amount received: {format_amount(amount_received)} {esc(currency)}"
    )
    if photo_count:
        text += f"\nAttachments: {photo_count}"
    return text


@router.message(F.text == FIAT_TRANSACTION)
@router.message(Command(CMD_FIAT_TRANSACTION))
async def start_fiat_transaction(message: Message, role: str | None, state: FSMContext) -> None:
    if role != "executor":
        return
    async with get_session() as session:
        available_wallets = await wallet_service.list_wallets(session)
    if not available_wallets:
        await message.answer("No wallets available yet. Add one first.")
        return
    await state.set_state(FiatTransactionStates.choosing_wallet)
    await message.answer("Choose wallet:", reply_markup=wallet_picker(available_wallets))


@router.callback_query(FiatTransactionStates.choosing_wallet, F.data.startswith("wallet:"))
async def choose_wallet(callback: CallbackQuery, state: FSMContext) -> None:
    wallet_id = int(callback.data.split(":", 1)[1])
    await state.update_data(wallet_id=wallet_id)
    await state.set_state(FiatTransactionStates.entering_sum)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Sum (USDT) — amount to write off from the wallet balance:")
    await callback.answer()


@router.message(FiatTransactionStates.entering_sum)
async def enter_sum(message: Message, state: FSMContext) -> None:
    try:
        amount = parse_amount(message.text or "")
    except ValueError:
        await message.answer("Please enter a valid positive number for Sum (USDT).")
        return
    await state.update_data(sum_usdt=str(amount))
    await state.set_state(FiatTransactionStates.entering_received)
    await message.answer("Amount received (bank or cash):")


@router.message(FiatTransactionStates.entering_received)
async def enter_received(message: Message, state: FSMContext) -> None:
    try:
        amount = parse_amount(message.text or "")
    except ValueError:
        await message.answer("Please enter a valid positive number for Amount received.")
        return
    await state.update_data(amount_received=str(amount))
    await state.set_state(FiatTransactionStates.choosing_currency)
    await message.answer("Currency:", reply_markup=currency_picker())


@router.callback_query(FiatTransactionStates.choosing_currency, F.data.startswith("currency:"))
async def choose_currency(callback: CallbackQuery, state: FSMContext) -> None:
    currency = callback.data.split(":", 1)[1]
    await callback.message.edit_reply_markup(reply_markup=None)
    prompt = await callback.message.answer(
        "Attach screenshot(s) of the bank transaction report, or press Done to skip.",
        reply_markup=done_keyboard(),
    )
    await state.update_data(currency=currency, report_file_ids=[], prompt_message_id=prompt.message_id)
    await state.set_state(FiatTransactionStates.attaching_report)
    await callback.answer()


async def _show_fiat_summary(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    async with get_session() as session:
        wallet = await wallet_service.get_wallet(session, data["wallet_id"])
    photos = data.get("report_file_ids", [])
    summary = _fiat_summary_text(
        wallet.address, data["sum_usdt"], data["amount_received"], data["currency"], len(photos)
    )
    await state.set_state(FiatTransactionStates.confirming)
    await message.answer(summary, reply_markup=confirm_keyboard())


@router.message(FiatTransactionStates.attaching_report, F.photo)
async def receive_fiat_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    photos = list(data.get("report_file_ids", []))
    photos.append(message.photo[-1].file_id)
    await state.update_data(report_file_ids=photos)
    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=data["prompt_message_id"],
        text=f"Photo added ({len(photos)}). Send another, or press Done.",
        reply_markup=done_keyboard(),
    )


@router.callback_query(FiatTransactionStates.attaching_report, F.data == "done_photos")
async def finish_fiat_photos(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await _show_fiat_summary(callback.message, state)
    await callback.answer()


@router.message(FiatTransactionStates.attaching_report)
async def receive_fiat_photo_wrong_content(message: Message) -> None:
    await message.answer("Please send a photo, or press Done.")


@router.callback_query(FiatTransactionStates.confirming, F.data == "cancel")
async def cancel_fiat_transaction(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Canceled.", reply_markup=executor_menu())
    await callback.answer()


@router.callback_query(FiatTransactionStates.confirming, F.data == "confirm")
async def confirm_fiat_transaction(
    callback: CallbackQuery, state: FSMContext, bot: Bot, config: Config
) -> None:
    data = await state.get_data()
    photos = data.get("report_file_ids", [])
    async with get_session() as session:
        try:
            tx = await wallet_service.create_fiat_transaction(
                session,
                data["wallet_id"],
                Decimal(data["sum_usdt"]),
                Decimal(data["amount_received"]),
                Currency(data["currency"]),
                photos,
            )
        except wallet_service.InsufficientFundsError:
            await state.clear()
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer(
                "There are not enough funds on the wallet balance", reply_markup=executor_menu()
            )
            await callback.answer()
            return
        wallet = await wallet_service.get_wallet(session, data["wallet_id"])

    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Fiat transaction recorded.", reply_markup=executor_menu())

    caption = (
        "<b>Fiat transaction completed</b>\n"
        f"Datetime: {fmt_dt(tx.created_at)}\n"
        f"Wallet: {esc(wallet.address)}\n"
        f"Sum (USDT): {format_amount(tx.sum_usdt)}\n"
        f"Amount received: {format_amount(tx.amount_received)} {esc(tx.currency.value)}"
    )
    await post_photos_to_group(bot, config, photos, caption)
    await callback.answer()
