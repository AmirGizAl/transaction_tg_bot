from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.keyboards.menus import executor_menu, owner_menu

router = Router()
router.message.filter(F.chat.type == "private")


@router.message(CommandStart())
async def cmd_start(message: Message, role: str | None) -> None:
    if role == "owner":
        await message.answer("Welcome, Owner. Choose an action:", reply_markup=owner_menu())
    elif role == "executor":
        await message.answer("Welcome, Executor. Choose an action:", reply_markup=executor_menu())
    else:
        await message.answer("Access denied. This bot is private.")
