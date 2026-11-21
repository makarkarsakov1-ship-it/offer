import asyncio
import logging
import os
import secrets

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

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
    "inline_query",
    "callback_query",
    "pre_checkout_query",
    "business_connection",
    "business_message",
    "edited_business_message",
    "deleted_business_messages",
]
WEBHOOK_PATH = "/telegram/webhook"


async def healthcheck(_: web.Request) -> web.Response:
    return web.Response(text="ok")


async def main() -> None:
    if not os.getenv("BOT_TOKEN", "").strip():
        log.warning("BOT_TOKEN is empty; starting health endpoint only. Add BOT_TOKEN in Render Environment and restart.")
        app = web.Application()
        app.router.add_get("/healthz", healthcheck)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
        try:
            await site.start()
            log.info("health-only server listening; Telegram webhook is not active until BOT_TOKEN is set")
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()
        return

    config = load_config()
    await db.init_db(config.database_path)

    external_url = os.getenv("WEBHOOK_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL")
    if not external_url:
        raise RuntimeError(
            "WEBHOOK_BASE_URL или RENDER_EXTERNAL_URL не задан. "
            "На Render RENDER_EXTERNAL_URL устанавливается автоматически."
        )
    webhook_url = f"{external_url.rstrip('/')}{WEBHOOK_PATH}"
    webhook_secret = os.getenv("WEBHOOK_SECRET", "").strip() or secrets.token_urlsafe(32)
    port = int(os.getenv("PORT", "10000"))

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
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

    async def on_startup(bot: Bot) -> None:
        await bot.set_webhook(
            url=webhook_url,
            allowed_updates=UPDATES,
            secret_token=webhook_secret,
            drop_pending_updates=False,
        )
        log.info("webhook configured for %s", external_url)

    async def on_shutdown(bot: Bot) -> None:
        await bot.session.close()

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    app.router.add_get("/healthz", healthcheck)
    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=webhook_secret,
    ).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    try:
        await site.start()
        log.info("webhook server listening on 0.0.0.0:%s", port)
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
