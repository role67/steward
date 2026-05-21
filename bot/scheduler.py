"""Планировщик напоминаний с поддержкой переноса (offset) на день."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from .db import Database
from .keyboards import daily_kb, reminder_kb
from .logic import (
    apply_punishments_for_today,
    auto_close_previous_day,
    get_today_context,
    render_day_plan,
)
from .plan import MORNING_LOG, REMINDERS, Reminder, find_reminder

log = logging.getLogger(__name__)


# ---------- helpers ----------
async def _send(bot: Bot, owner_id: int, text: str, **kwargs) -> None:
    try:
        await bot.send_message(owner_id, text, **kwargs)
    except TelegramAPIError as e:
        log.warning("send failed: %s", e)


def _today_base_dt(rem: Reminder, tz, today=None) -> datetime:
    """datetime сегодня по базовому расписанию (без оффсета)."""
    today = today or datetime.now(tz).date()
    return datetime(today.year, today.month, today.day, rem.hour, rem.minute, tzinfo=tz)


def _oneshot_id(key: str, day: str) -> str:
    return f"oneshot_{key}_{day}"


# ---------- core: send a reminder ----------
async def fire_reminder(bot: Bot, owner_id: int, db: Database, tz, key: str) -> None:
    """Отправляет конкретное напоминание (вызывается и cron-ом, и one-shot-ом)."""
    today = datetime.now(tz).date()

    if key == MORNING_LOG.key:
        await _job_morning(bot, owner_id, db, tz)
        return
    if key == "start_home":
        await _job_start_home(bot, owner_id, db, tz)
        return

    # На воскресенье оставляем только «дисциплинарные» напоминания
    if today.weekday() == 6 and key not in {"snack", "prep_sleep", "shower", "sleep"}:
        return

    rem = find_reminder(key)
    if not rem:
        return
    offset = await db.get_offset(owner_id, today)
    kb = reminder_kb(key, rem.postponable, offset)
    suffix = f"\n\n<i>Сдвиг сегодня: +{offset} мин</i>" if offset else ""
    await _send(bot, owner_id, rem.text + suffix, reply_markup=kb)


async def _maybe_fire_cron(bot: Bot, owner_id: int, db: Database, tz, key: str) -> None:
    """Cron-обёртка: если на сегодня есть оффсет — пропустить (one-shot отстреляет)."""
    today = datetime.now(tz).date()
    offset = await db.get_offset(owner_id, today)
    if offset > 0:
        return
    await fire_reminder(bot, owner_id, db, tz, key)


# ---------- jobs ----------
async def _job_start_home(bot: Bot, owner_id: int, db: Database, tz) -> None:
    today = datetime.now(tz).date()
    if today.weekday() == 6:
        return
    await auto_close_previous_day(db, owner_id, today)
    delta = await apply_punishments_for_today(db, owner_id, today)
    week, weekday, plan, ec, eb, row = await get_today_context(db, owner_id, today)
    offset = await db.get_offset(owner_id, today)

    head = "🏠 <b>СТАРТ домашней тренировки.</b>\n"
    if delta:
        head += f"⚠️ {delta.reason}\n"
    if offset:
        head += f"⏰ Сегодня сдвиг: <b>+{offset} мин</b>\n"
    text = head + "\n" + render_day_plan(today, week, plan, ec, eb)
    kb = daily_kb(row["home_done"], row["bike_done"], row["pullups_done"],
                  is_rest=plan.rest, status=row["status"])
    await _send(bot, owner_id, text, reply_markup=kb)


async def _job_morning(bot: Bot, owner_id: int, db: Database, tz) -> None:
    today = datetime.now(tz).date()
    await auto_close_previous_day(db, owner_id, today)
    delta = await apply_punishments_for_today(db, owner_id, today)
    text = "📊 Доброе утро. Запиши вес и сколько спал.\n/weight 78.5\n/sleep 7.5"
    if delta:
        text = f"⚠️ {delta.reason}\n\n" + text
    await _send(bot, owner_id, text)


async def _midnight_close(bot: Bot, owner_id: int, db: Database, tz) -> None:
    today = datetime.now(tz).date()
    await auto_close_previous_day(db, owner_id, today)
    # Чистим вчерашний оффсет, чтобы новый день начинался с 0
    yesterday = today - timedelta(days=1)
    await db.reset_offset(owner_id, yesterday)


# ---------- public: reschedule on offset change ----------
async def reschedule_today(
    sched: AsyncIOScheduler, bot: Bot, owner_id: int, db: Database, tz,
) -> None:
    """Удаляет все one-shot джобы на сегодня и заново ставит их с учётом текущего оффсета."""
    today = datetime.now(tz).date()
    today_str = today.isoformat()
    offset = await db.get_offset(owner_id, today)

    all_keys = [r.key for r in REMINDERS]
    for key in all_keys:
        try:
            sched.remove_job(_oneshot_id(key, today_str))
        except JobLookupError:
            pass

    if offset <= 0:
        return  # cron сам отстреляет

    now = datetime.now(tz)
    for rem in REMINDERS:
        run_at = _today_base_dt(rem, tz, today) + timedelta(minutes=offset)
        if run_at <= now:
            continue
        sched.add_job(
            fire_reminder,
            DateTrigger(run_date=run_at, timezone=tz),
            args=[bot, owner_id, db, tz, rem.key],
            id=_oneshot_id(rem.key, today_str),
            replace_existing=True,
            misfire_grace_time=60,
        )


# ---------- setup ----------
def setup_scheduler(bot: Bot, owner_id: int, db: Database, tz) -> AsyncIOScheduler:
    sched = AsyncIOScheduler(timezone=tz)

    for r in REMINDERS:
        sched.add_job(
            _maybe_fire_cron,
            CronTrigger(hour=r.hour, minute=r.minute, timezone=tz),
            args=[bot, owner_id, db, tz, r.key],
            id=f"rem_{r.key}", replace_existing=True,
            misfire_grace_time=120,
        )

    sched.add_job(
        _maybe_fire_cron,
        CronTrigger(hour=MORNING_LOG.hour, minute=MORNING_LOG.minute, timezone=tz),
        args=[bot, owner_id, db, tz, MORNING_LOG.key],
        id="rem_morning", replace_existing=True,
    )

    sched.add_job(
        _midnight_close,
        CronTrigger(hour=0, minute=5, timezone=tz),
        args=[bot, owner_id, db, tz],
        id="midnight_close", replace_existing=True,
    )

    return sched
