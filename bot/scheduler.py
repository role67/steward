"""Планировщик напоминаний."""
from __future__ import annotations

import logging
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .db import Database
from .keyboards import daily_kb
from .logic import (
    apply_punishments_for_today,
    auto_close_previous_day,
    get_today_context,
    render_day_plan,
)
from .plan import MORNING_LOG, REMINDERS

log = logging.getLogger(__name__)


async def _send(bot: Bot, owner_id: int, text: str, **kwargs) -> None:
    try:
        await bot.send_message(owner_id, text, **kwargs)
    except TelegramAPIError as e:
        log.warning("send failed: %s", e)


async def job_reminder(bot: Bot, owner_id: int, db: Database, tz, key: str, text: str) -> None:
    # На воскресенье отключаем все, кроме утреннего и сна.
    today = datetime.now(tz).date()
    if today.weekday() == 6 and key not in {"morning_log", "snack", "prep_sleep", "shower", "sleep"}:
        return
    await _send(bot, owner_id, text)


async def job_start_home(bot: Bot, owner_id: int, db: Database, tz) -> None:
    today = datetime.now(tz).date()
    await auto_close_previous_day(db, owner_id, today)
    delta = await apply_punishments_for_today(db, owner_id, today)
    week, weekday, plan, ec, eb, row = await get_today_context(db, owner_id, today)

    head = "🏠 <b>СТАРТ домашней тренировки.</b>\n"
    if delta:
        head += f"⚠️ {delta.reason}\n"
    text = head + "\n" + render_day_plan(today, week, plan, ec, eb)
    kb = daily_kb(row["home_done"], row["bike_done"], row["pullups_done"], is_rest=plan.rest)
    await _send(bot, owner_id, text, reply_markup=kb)


async def job_morning(bot: Bot, owner_id: int, db: Database, tz) -> None:
    today = datetime.now(tz).date()
    # «Закрытие» вчерашнего дня + начисление наказаний при утре
    await auto_close_previous_day(db, owner_id, today)
    delta = await apply_punishments_for_today(db, owner_id, today)
    text = "📊 Доброе утро. Запиши вес и сколько спал.\n/weight 78.5\n/sleep 7.5"
    if delta:
        text = f"⚠️ {delta.reason}\n\n" + text
    await _send(bot, owner_id, text)


def setup_scheduler(bot: Bot, owner_id: int, db: Database, tz) -> AsyncIOScheduler:
    sched = AsyncIOScheduler(timezone=tz)

    for r in REMINDERS:
        if r.key == "start_home":
            sched.add_job(
                job_start_home,
                CronTrigger(hour=r.hour, minute=r.minute, timezone=tz),
                args=[bot, owner_id, db, tz],
                id=f"rem_{r.key}", replace_existing=True,
            )
        else:
            sched.add_job(
                job_reminder,
                CronTrigger(hour=r.hour, minute=r.minute, timezone=tz),
                args=[bot, owner_id, db, tz, r.key, r.text],
                id=f"rem_{r.key}", replace_existing=True,
            )

    # Утреннее напоминание
    sched.add_job(
        job_morning,
        CronTrigger(hour=MORNING_LOG.hour, minute=MORNING_LOG.minute, timezone=tz),
        args=[bot, owner_id, db, tz],
        id="rem_morning", replace_existing=True,
    )

    # Полуночное закрытие дня (на всякий случай)
    sched.add_job(
        _midnight_close,
        CronTrigger(hour=0, minute=5, timezone=tz),
        args=[bot, owner_id, db, tz],
        id="midnight_close", replace_existing=True,
    )

    return sched


async def _midnight_close(bot: Bot, owner_id: int, db: Database, tz) -> None:
    today = datetime.now(tz).date()
    await auto_close_previous_day(db, owner_id, today)
