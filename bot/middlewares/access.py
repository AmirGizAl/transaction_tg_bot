from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.config import Config


class RoleMiddleware(BaseMiddleware):
    def __init__(self, config: Config):
        self.config = config

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        role = None
        if user is not None:
            if user.id == self.config.owner_id:
                role = "owner"
            elif user.id == self.config.executor_id:
                role = "executor"
        data["role"] = role
        data["config"] = self.config
        return await handler(event, data)
