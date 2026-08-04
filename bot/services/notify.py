from aiogram import Bot
from aiogram.types import InputMediaPhoto

from bot.config import Config


async def post_to_group(bot: Bot, config: Config, text: str, reply_markup=None) -> int:
    message = await bot.send_message(config.group_chat_id, text, reply_markup=reply_markup)
    return message.message_id


async def post_photo_to_group(bot: Bot, config: Config, photo_file_id: str, caption: str) -> int:
    message = await bot.send_photo(config.group_chat_id, photo=photo_file_id, caption=caption)
    return message.message_id


async def post_photos_to_group(bot: Bot, config: Config, file_ids: list[str], caption: str) -> None:
    if not file_ids:
        await post_to_group(bot, config, caption)
    elif len(file_ids) == 1:
        await post_photo_to_group(bot, config, file_ids[0], caption)
    else:
        media = [InputMediaPhoto(media=file_id) for file_id in file_ids]
        media[0] = InputMediaPhoto(media=media[0].media, caption=caption)
        await bot.send_media_group(config.group_chat_id, media=media)
