import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError

from bot.config import load_config
from bot.db.engine import init_db, init_engine
from bot.fsm_storage import storage
from bot.handlers import balance, fiat, onchain, report, start, transfer, wallet
from bot.middlewares.access import RoleMiddleware

logger = logging.getLogger(__name__)


async def _delete_webhook_with_retry(bot: Bot, attempts: int = 10, delay: float = 5.0) -> None:
    for attempt in range(1, attempts + 1):
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            return
        except TelegramNetworkError as exc:
            logger.warning("Cannot reach Telegram yet (attempt %s/%s): %s", attempt, attempts, exc)
            if attempt == attempts:
                logger.warning("Giving up on delete_webhook, proceeding to polling anyway")
                return
            await asyncio.sleep(delay)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    config = load_config()

    init_engine(config.db_path)
    await init_db()

    session = AiohttpSession(proxy=config.proxy_url) if config.proxy_url else None

    async with Bot(
        token=config.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    ) as bot:
        dp = Dispatcher(storage=storage)

        role_middleware = RoleMiddleware(config)
        dp.message.middleware(role_middleware)
        dp.callback_query.middleware(role_middleware)

        dp.include_router(start.router)
        dp.include_router(onchain.router)
        dp.include_router(fiat.router)
        dp.include_router(wallet.router)
        dp.include_router(balance.router)
        dp.include_router(transfer.router)
        dp.include_router(report.router)

        await _delete_webhook_with_retry(bot)
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
