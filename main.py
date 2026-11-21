import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent

from bot import database as db
from bot.config import Config, load_config
from bot.handlers import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("nft-business-bot")

UPDATES = [
    "message",
    "callback_query",
    "business_connection",
    "business_message",
    "edited_business_message",
    "deleted_business_messages",
]


async def main() -> None:
    config = load_config()
    await db.init_db(config.database_path)

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(config=config)
    dp.include_router(router)

    @dp.error()
    async def on_error(event: ErrorEvent, bot: Bot, config: Config):
        log.exception("unhandled error", exc_info=event.exception)
        if config.admin_id:
            try:
                await bot.send_message(
                    config.admin_id,
                    f"Ошибка: {type(event.exception).__name__}: {event.exception}"[:3500],
                    parse_mode=None,
                )
            except Exception:
                log.exception("failed to notify admin")
        return True

    await bot.delete_webhook(drop_pending_updates=False)
    log.info("starting long polling")
    await dp.start_polling(bot, allowed_updates=UPDATES)


if __name__ == "__main__":
    asyncio.run(main())
