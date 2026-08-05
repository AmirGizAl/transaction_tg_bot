from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.db.engine import get_session
from bot.keyboards.inline import period_picker
from bot.keyboards.menus import CMD_DOWNLOAD_REPORT, DOWNLOAD_REPORT
from bot.services import reports

router = Router()
router.message.filter(F.chat.type == "private")


@router.message(F.text == DOWNLOAD_REPORT)
@router.message(Command(CMD_DOWNLOAD_REPORT))
async def start_report(message: Message, role: str | None) -> None:
    if role not in ("owner", "executor"):
        return
    await message.answer("Choose period:", reply_markup=period_picker())


@router.callback_query(F.data.startswith("period:"))
async def send_report(callback: CallbackQuery, role: str | None) -> None:
    if role not in ("owner", "executor"):
        await callback.answer()
        return
    period = callback.data.split(":", 1)[1]
    async with get_session() as session:
        buffer = await reports.build_report(session, period)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer_document(
        BufferedInputFile(buffer.read(), filename=f"report_{period}.xlsx"),
        caption=f"Report for the last {period}.",
    )
    await callback.answer()
