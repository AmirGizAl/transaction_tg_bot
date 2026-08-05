import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from bot.config import MSK, Config, load_config
from bot.db.engine import init_db, init_engine
from bot.fsm_storage import storage
from bot.handlers import balance, fiat, onchain, report, start, transfer, wallet
from bot.keyboards.menus import (
    CMD_ADD_WALLET,
    CMD_CHANGE_BALANCE,
    CMD_DELETE_WALLET,
    CMD_DOWNLOAD_REPORT,
    CMD_FIAT_TRANSACTION,
    CMD_NEW_TRANSACTION,
    CMD_TRANSFER_BETWEEN_WALLETS,
)
from bot.middlewares.access import RoleMiddleware

logger = logging.getLogger(__name__)


class MskFormatter(logging.Formatter):
    """Formats log timestamps in MSK (UTC+3), regardless of the host/container timezone."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=MSK)
        return dt.strftime(datefmt or "%Y-%m-%d %H:%M:%S %Z")


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


async def _set_commands(bot: Bot, config: Config) -> None:
    """Register the "/" commands menu as a fallback entry point that doesn't depend on the
    reply keyboard being visible. Scoped per-user since Owner and Executor have different
    actions available."""
    try:
        await bot.set_my_commands(
            [BotCommand(command="start", description="Show the menu")],
            scope=BotCommandScopeDefault(),
        )
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Show the menu"),
                BotCommand(command=CMD_NEW_TRANSACTION, description="New transaction"),
                BotCommand(command=CMD_DOWNLOAD_REPORT, description="Download report"),
            ],
            scope=BotCommandScopeChat(chat_id=config.owner_id),
        )
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Show the menu"),
                BotCommand(command=CMD_FIAT_TRANSACTION, description="Fiat transaction"),
                BotCommand(command=CMD_ADD_WALLET, description="Add wallet"),
                BotCommand(command=CMD_DELETE_WALLET, description="Delete wallet"),
                BotCommand(command=CMD_CHANGE_BALANCE, description="Change balance"),
                BotCommand(command=CMD_TRANSFER_BETWEEN_WALLETS, description="Tr. between wallets"),
                BotCommand(command=CMD_DOWNLOAD_REPORT, description="Download report"),
            ],
            scope=BotCommandScopeChat(chat_id=config.executor_id),
        )
    except TelegramNetworkError as exc:
        logger.warning("Could not register bot commands (will retry on next restart): %s", exc)


async def main() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(MskFormatter("%(asctime)s %(levelname)s:%(name)s:%(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
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
        await _set_commands(bot, config)
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
