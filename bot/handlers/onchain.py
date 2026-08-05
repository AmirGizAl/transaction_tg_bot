from decimal import Decimal

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.db.engine import get_session
from bot.db.models import RequestStatus
from bot.fsm_storage import storage
from bot.keyboards.inline import confirm_keyboard, done_keyboard, request_card_keyboard, wallet_picker
from bot.keyboards.menus import CMD_NEW_TRANSACTION, NEW_TRANSACTION, owner_menu
from bot.services import wallets as wallet_service
from bot.services.notify import post_photos_to_group, post_to_group
from bot.utils import esc, fmt_dt, format_amount, parse_amount

router = Router()
router.message.filter(F.chat.type == "private")


class NewTransactionStates(StatesGroup):
    choosing_wallet = State()
    entering_sum = State()
    entering_recipient = State()
    confirming = State()


class AttachReportStates(StatesGroup):
    collecting_photos = State()
    confirming = State()


def _onchain_card_text(status: str, created_at_text: str, wallet_address: str, amount, recipient: str) -> str:
    return (
        "<b>Onchain transaction request</b>\n"
        f"Status: {esc(status)}\n"
        f"Created: {esc(created_at_text)}\n"
        f"Wallet: {esc(wallet_address)}\n"
        f"Sum: {format_amount(amount)} USDT\n"
        f"Recipient: {esc(recipient)}"
    )


@router.message(F.text == NEW_TRANSACTION)
@router.message(Command(CMD_NEW_TRANSACTION))
async def start_new_transaction(message: Message, role: str | None, state: FSMContext) -> None:
    if role != "owner":
        return
    async with get_session() as session:
        available_wallets = await wallet_service.list_wallets(session)
    if not available_wallets:
        await message.answer("No wallets available yet. Ask the Executor to add one first.")
        return
    await state.set_state(NewTransactionStates.choosing_wallet)
    await message.answer("Choose wallet:", reply_markup=wallet_picker(available_wallets))


@router.callback_query(NewTransactionStates.choosing_wallet, F.data.startswith("wallet:"))
async def choose_wallet(callback: CallbackQuery, state: FSMContext) -> None:
    wallet_id = int(callback.data.split(":", 1)[1])
    await state.update_data(wallet_id=wallet_id)
    await state.set_state(NewTransactionStates.entering_sum)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Sum (USDT):")
    await callback.answer()


@router.message(NewTransactionStates.entering_sum)
async def enter_sum(message: Message, state: FSMContext) -> None:
    try:
        amount = parse_amount(message.text or "")
    except ValueError:
        await message.answer("Please enter a valid positive number for Sum (USDT).")
        return
    await state.update_data(amount=str(amount))
    await state.set_state(NewTransactionStates.entering_recipient)
    await message.answer("Recipient wallet:")


@router.message(NewTransactionStates.entering_recipient)
async def enter_recipient(message: Message, state: FSMContext) -> None:
    recipient = (message.text or "").strip()
    if not recipient:
        await message.answer("Please enter a recipient wallet address.")
        return
    data = await state.update_data(recipient=recipient)
    async with get_session() as session:
        wallet = await wallet_service.get_wallet(session, data["wallet_id"])
    summary = _onchain_card_text(
        "In progress (not yet created)",
        "-",
        wallet.address,
        data["amount"],
        recipient,
    )
    await state.set_state(NewTransactionStates.confirming)
    await message.answer(summary, reply_markup=confirm_keyboard())


@router.callback_query(NewTransactionStates.confirming, F.data == "cancel")
async def cancel_new_transaction(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Canceled.", reply_markup=owner_menu())
    await callback.answer()


@router.callback_query(NewTransactionStates.confirming, F.data == "confirm")
async def confirm_new_transaction(callback: CallbackQuery, state: FSMContext, bot: Bot, config: Config) -> None:
    data = await state.get_data()
    async with get_session() as session:
        try:
            request = await wallet_service.create_onchain_request(
                session, data["wallet_id"], Decimal(data["amount"]), data["recipient"]
            )
        except wallet_service.InsufficientFundsError:
            await state.clear()
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer(
                "There are not enough funds on the wallet balance", reply_markup=owner_menu()
            )
            await callback.answer()
            return
        wallet = await wallet_service.get_wallet(session, data["wallet_id"])

    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Request created.", reply_markup=owner_menu())

    card_text = _onchain_card_text(
        "In progress", fmt_dt(request.created_at), wallet.address, request.sum, request.recipient_wallet
    )
    group_message_id = await post_to_group(bot, config, card_text, reply_markup=request_card_keyboard(request.id))
    async with get_session() as session:
        req = await wallet_service.get_onchain_request(session, request.id)
        req.group_message_id = group_message_id
        await session.commit()
    await callback.answer()


@router.callback_query(F.data.startswith("req_cancel:"))
async def cancel_request(callback: CallbackQuery, config: Config) -> None:
    if callback.from_user.id != config.owner_id:
        await callback.answer("Only the Owner can cancel this request.", show_alert=True)
        return
    request_id = int(callback.data.split(":", 1)[1])
    async with get_session() as session:
        request = await wallet_service.get_onchain_request(session, request_id)
        if request.status != RequestStatus.IN_PROGRESS:
            await callback.answer("This request can no longer be canceled.", show_alert=True)
            return
        request = await wallet_service.cancel_onchain_request(session, request_id)
        wallet = await wallet_service.get_wallet(session, request.wallet_id)

    card_text = _onchain_card_text(
        "Canceled", fmt_dt(request.created_at), wallet.address, request.sum, request.recipient_wallet
    )
    await callback.message.edit_text(card_text, reply_markup=None)
    await callback.answer("Request canceled.")


@router.callback_query(F.data.startswith("req_attach:"))
async def start_attach_report(callback: CallbackQuery, bot: Bot, config: Config) -> None:
    if callback.from_user.id != config.executor_id:
        await callback.answer("Only the Executor can attach a report.", show_alert=True)
        return
    request_id = int(callback.data.split(":", 1)[1])
    async with get_session() as session:
        request = await wallet_service.get_onchain_request(session, request_id)
        if request.status != RequestStatus.IN_PROGRESS:
            await callback.answer("This request is already resolved.", show_alert=True)
            return

    prompt = await bot.send_message(
        config.executor_id,
        f"Send one or more photos of the transaction report for request #{request_id}, "
        "then press Done.",
        reply_markup=done_keyboard(),
    )

    executor_key = StorageKey(bot_id=bot.id, chat_id=config.executor_id, user_id=config.executor_id)
    executor_state = FSMContext(storage=storage, key=executor_key)
    await executor_state.set_state(AttachReportStates.collecting_photos)
    await executor_state.update_data(request_id=request_id, photos=[], prompt_message_id=prompt.message_id)
    await callback.answer("Check your private chat with the bot.")


@router.message(AttachReportStates.collecting_photos, F.photo)
async def receive_report_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    photos = list(data.get("photos", []))
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=data["prompt_message_id"],
        text=f"Photo added ({len(photos)}). Send another, or press Done.",
        reply_markup=done_keyboard(),
    )


@router.message(AttachReportStates.collecting_photos)
async def receive_report_wrong_content(message: Message) -> None:
    await message.answer("Please send a photo of the transaction report, or press Done.")


@router.callback_query(AttachReportStates.collecting_photos, F.data == "done_photos")
async def finish_collecting_photos(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    photos = data.get("photos", [])
    if not photos:
        await callback.answer("Attach at least one photo first.", show_alert=True)
        return
    await state.set_state(AttachReportStates.confirming)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"{len(photos)} photo(s) attached. Confirm?", reply_markup=confirm_keyboard())
    await callback.answer()


@router.callback_query(AttachReportStates.confirming, F.data == "cancel")
async def cancel_attach_report(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Attaching the report was canceled. Click \"Attach a report\" again if needed.")
    await callback.answer()


@router.callback_query(AttachReportStates.confirming, F.data == "confirm")
async def confirm_attach_report(callback: CallbackQuery, state: FSMContext, bot: Bot, config: Config) -> None:
    data = await state.get_data()
    request_id = data["request_id"]
    photos = data["photos"]

    async with get_session() as session:
        request = await wallet_service.settle_onchain_request(session, request_id, photos)
        wallet = await wallet_service.get_wallet(session, request.wallet_id)

    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Report attached. Request marked as Done.")

    card_text = _onchain_card_text(
        "Done", fmt_dt(request.created_at), wallet.address, request.sum, request.recipient_wallet
    )
    if request.group_message_id is not None:
        await bot.edit_message_text(
            chat_id=config.group_chat_id,
            message_id=request.group_message_id,
            text=card_text,
            reply_markup=None,
        )
    caption = (
        f"<b>Report for request #{request.id}</b>\n"
        f"Done, {esc(wallet.address)}, {format_amount(request.sum)} USDT"
    )
    await post_photos_to_group(bot, config, photos, caption)
    await callback.answer()
