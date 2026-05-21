"""Inline-управление дневной тренировкой."""
from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.types import CallbackQuery

from ..db import Database
from ..keyboards import daily_kb
from ..logic import get_today_context, render_day_plan

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
    kb = daily_kb(row["home_done"], row["bike_done"], row["pullups_done"], is_rest=plan.rest)
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
