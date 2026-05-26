"""Entry point: bot + web server + scheduler."""
from __future__ import annotations

import asyncio
import logging
import platform
import signal
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

try:
    from .config import load_settings
    from .db import Database
    from .handlers import build_router
    from .scheduler import setup_scheduler
    from .web import run_web
except ImportError:
    # Fallback for direct execution: python bot/main.py
    from bot.config import load_settings
    from bot.db import Database
    from bot.handlers import build_router
    from bot.scheduler import setup_scheduler
    from bot.web import run_web


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("dayliki")


async def main() -> None:
    log.info(
        "Booting dayliki (python=%s, platform=%s, argv=%s)",
        sys.version.split()[0],
        platform.platform(),
        " ".join(sys.argv),
    )
    settings = load_settings()

    db = Database(settings.database_url)
    await db.connect()
    await db.ensure_user(settings.owner_id, settings.tz_name)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(build_router())

    @dp.error()
    async def on_error(event):
        log.exception("Unhandled update error: %r", event.exception)
        return True

    scheduler = setup_scheduler(bot, settings.owner_id, db, settings.tz)
    scheduler.start()
    log.info("Scheduler started (tz=%s)", settings.tz_name)

    deps = dict(
        db=db,
        owner_id=settings.owner_id,
        tz=settings.tz,
        tz_name=settings.tz_name,
        scheduler=scheduler,
    )

    web_runner = await run_web("0.0.0.0", settings.port, settings.public_url)

    try:
        await bot.delete_webhook(drop_pending_updates=False)
    except Exception as e:
        log.warning("delete_webhook failed: %s", e)

    stop_event = asyncio.Event()

    def _signal_handler(*_: object) -> None:
        log.info("Stop signal received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass

    polling_task = asyncio.create_task(dp.start_polling(bot, **deps))
    stop_task = asyncio.create_task(stop_event.wait())
    _, pending = await asyncio.wait(
        {polling_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
    )

    log.info("Shutting down...")
    for task in pending:
        task.cancel()
    try:
        await dp.stop_polling()
    except Exception:
        pass
    scheduler.shutdown(wait=False)
    await web_runner.cleanup()
    await bot.session.close()
    await db.close()
    log.info("Bye.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        log.exception("Fatal startup/runtime error: %s", e)
        sys.exit(1)
