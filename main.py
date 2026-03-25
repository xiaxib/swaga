import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config.logging_config import setup_logging
from config.settings import get_settings
from database.init_db import init_db
from handlers import admin, commands, tasks
from middlewares.db import DbSessionMiddleware


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    init_db()

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.message.middleware(DbSessionMiddleware())
    dp.callback_query.middleware(DbSessionMiddleware())

    dp.include_router(commands.router)
    dp.include_router(admin.router)
    dp.include_router(tasks.router)

    logging.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
