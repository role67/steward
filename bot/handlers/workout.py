"""Inline-управление дневной тренировкой."""
from __future__ import annotations

from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..db import Database
from ..keyboards import daily_kb
from ..logic import get_today_context, render_day_plan
from ..scheduler import reschedule_today

router = Router(name="workout")


async def _refresh(cb: CallbackQuery, db: Database, owner_id: int, tz):
    today = datetime.now(tz).date()
    week, weekday, plan, ec, eb, row = await get_today_context(db, owner_id, today)
    text = render_day_plan(today, week, plan, ec, eb)

    status = row["status"]
    suffix = {
        "done":    "\n\n✅ <b>День закрыт. Красава.</b>",
        "minimum": "\n\n🟡 <b>Сделан минимум. Лучше, чем ноль.</b>",
        "missed":  "\n\n❌ <b>Пропуск зафиксирован.</b> Завтра +1 круг, +15 мин велик.",
        "rest":    "\n\n🛌 <b>Отдых.</b>",
    }.get(status, "")

    offset = await db.get_offset(owner_id, today)
    if offset:
        suffix += f"\n⏰ Сдвиг расписания: <b>+{offset} мин</b>"

    kb = daily_kb(row["home_done"], row["bike_done"], row["pullups_done"],
                  is_rest=plan.rest, status=status)
    try:
        await cb.message.edit_text(text + suffix, reply_markup=kb)
    except Exception:
        pass


@router.callback_query(F.data.startswith("toggle:"))
async def cb_toggle(cb: CallbackQuery, db: Database, owner_id: int, tz):
    if cb.from_user.id != owner_id:
        await cb.answer(); return
    today = datetime.now(tz).date()
    field = {"toggle:home": "home_done", "toggle:bike": "bike_done", "toggle:pullups": "pullups_done"}[cb.data]
    await get_today_context(db, owner_id, today)  # ensure row exists
    new_val = await db.toggle_daily_flag(owner_id, today, field)
    await cb.answer("Отмечено ✅" if new_val else "Снято ❌")
    await _refresh(cb, db, owner_id, tz)


@router.callback_query(F.data == "daily:done")
async def cb_done(cb: CallbackQuery, db: Database, owner_id: int, tz):
    if cb.from_user.id != owner_id:
        await cb.answer(); return
    today = datetime.now(tz).date()
    await get_today_context(db, owner_id, today)
    await db.set_daily_status(owner_id, today, "done",
                              home_done=True, bike_done=True, pullups_done=True)
    await cb.answer("День закрыт 🔥")
    await _refresh(cb, db, owner_id, tz)


@router.callback_query(F.data == "daily:minimum")
async def cb_min(cb: CallbackQuery, db: Database, owner_id: int, tz):
    if cb.from_user.id != owner_id:
        await cb.answer(); return
    today = datetime.now(tz).date()
    await get_today_context(db, owner_id, today)
    await db.set_daily_status(owner_id, today, "minimum",
                              home_done=True, bike_done=True, circles=2, bike_minutes=30)
    await cb.answer("Минимум зачтён 🟡")
    await _refresh(cb, db, owner_id, tz)


@router.callback_query(F.data == "daily:missed")
async def cb_missed(cb: CallbackQuery, db: Database, owner_id: int, tz):
    if cb.from_user.id != owner_id:
        await cb.answer(); return
    today = datetime.now(tz).date()
    await get_today_context(db, owner_id, today)
    await db.set_daily_status(owner_id, today, "missed",
                              home_done=False, bike_done=False, pullups_done=False)
    await cb.answer("Пропуск. Завтра наказание.")
    await _refresh(cb, db, owner_id, tz)


@router.callback_query(F.data == "daily:refresh")
async def cb_refresh(cb: CallbackQuery, db: Database, owner_id: int, tz):
    if cb.from_user.id != owner_id:
        await cb.answer(); return
    await _refresh(cb, db, owner_id, tz)
    await cb.answer()


@router.callback_query(F.data == "daily:reopen")
async def cb_reopen(cb: CallbackQuery, db: Database, owner_id: int, tz):
    """Сброс статуса дня обратно в pending — отмена 'минимум/пропуск/закрыт'."""
    if cb.from_user.id != owner_id:
        await cb.answer(); return
    today = datetime.now(tz).date()
    await get_today_context(db, owner_id, today)
    await db.pool.execute(
        "UPDATE daily_logs SET status='pending', closed_at=NULL "
        "WHERE user_id=$1 AND log_date=$2",
        owner_id, today,
    )
    await cb.answer("День снова открыт ↩")
    await _refresh(cb, db, owner_id, tz)


# ---------- Перенос расписания ----------
@router.callback_query(F.data.startswith("postpone:"))
async def cb_postpone(
    cb: CallbackQuery, db: Database, owner_id: int, tz,
    bot: Bot, scheduler: AsyncIOScheduler,
):
    if cb.from_user.id != owner_id:
        await cb.answer(); return

    today = datetime.now(tz).date()
    parts = cb.data.split(":")
    action = parts[1]

    if action == "reset":
        await db.reset_offset(owner_id, today)
        await reschedule_today(scheduler, bot, owner_id, db, tz)
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await cb.message.answer("↩ Сдвиг сброшен. Расписание вернулось к базовому.")
        await cb.answer("Сброшено")
        return

    try:
        delta = int(action)
    except ValueError:
        await cb.answer(); return
    if delta not in (30, 60):
        await cb.answer(); return

    new_offset = await db.add_offset(owner_id, today, delta)
    await reschedule_today(scheduler, bot, owner_id, db, tz)

    try:
        # Снимем кнопки на этом сообщении, чтобы не нажимали повторно
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await cb.message.answer(
        f"⏰ Перенесено на <b>+{delta} мин</b>.\n"
        f"Текущий сдвиг сегодня: <b>+{new_offset} мин</b>.\n"
        f"Все оставшиеся напоминания сдвинуты."
    )
    await cb.answer(f"+{delta} мин")
