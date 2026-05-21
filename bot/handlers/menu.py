"""Старт, главное меню, статистика, план недели."""
from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from ..db import Database
from ..keyboards import back_kb, daily_kb, main_menu_kb, main_reply_kb
from ..logic import (
    apply_punishments_for_today,
    auto_close_previous_day,
    get_today_context,
    render_day_plan,
)
from ..plan import PLAN, WEEKDAY_NAMES, get_day_plan
from ..texts import ACCESS_DENIED, WELCOME

router = Router(name="menu")


def _own(owner_id: int):
    async def guard(message_or_cb) -> bool:
        uid = message_or_cb.from_user.id if message_or_cb.from_user else None
        return uid == owner_id
    return guard


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database, owner_id: int, tz_name: str):
    if message.from_user.id != owner_id:
        await message.answer(ACCESS_DENIED)
        return
    await db.ensure_user(owner_id, tz_name)
    await message.answer(WELCOME, reply_markup=main_reply_kb())
    await message.answer("📊 Открой меню:", reply_markup=main_menu_kb())


@router.message(Command("menu"))
@router.message(F.text == "🗓 Меню")
async def cmd_menu(message: Message, owner_id: int):
    if message.from_user.id != owner_id:
        return
    await message.answer("📊 Меню:", reply_markup=main_menu_kb())


@router.callback_query(F.data == "menu")
async def cb_menu(cb: CallbackQuery, owner_id: int):
    if cb.from_user.id != owner_id:
        await cb.answer(); return
    await cb.message.edit_text("📊 Меню:", reply_markup=main_menu_kb())
    await cb.answer()


# ---------- Сегодня ----------
async def _send_today(target, db: Database, owner_id: int, tz):
    today = datetime.now(tz).date()
    await auto_close_previous_day(db, owner_id, today)
    await apply_punishments_for_today(db, owner_id, today)
    week, weekday, plan, ec, eb, row = await get_today_context(db, owner_id, today)
    text = render_day_plan(today, week, plan, ec, eb)
    kb = daily_kb(
        home=row["home_done"], bike=row["bike_done"], pullups=row["pullups_done"],
        is_rest=plan.rest,
    )
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb)


@router.message(Command("today"))
@router.message(F.text == "📅 Сегодня")
async def cmd_today(message: Message, db: Database, owner_id: int, tz):
    if message.from_user.id != owner_id: return
    await _send_today(message, db, owner_id, tz)


@router.callback_query(F.data == "show:today")
async def cb_today(cb: CallbackQuery, db: Database, owner_id: int, tz):
    if cb.from_user.id != owner_id:
        await cb.answer(); return
    await _send_today(cb, db, owner_id, tz)


# ---------- Статистика ----------
@router.message(Command("stats"))
@router.message(F.text == "📈 Статистика")
async def cmd_stats(message: Message, db: Database, owner_id: int, tz):
    if message.from_user.id != owner_id: return
    await _send_stats(message, db, owner_id, tz)


@router.callback_query(F.data == "show:stats")
async def cb_stats(cb: CallbackQuery, db: Database, owner_id: int, tz):
    if cb.from_user.id != owner_id:
        await cb.answer(); return
    await _send_stats(cb, db, owner_id, tz)


async def _send_stats(target, db: Database, owner_id: int, tz):
    today = datetime.now(tz).date()
    since = today - timedelta(days=14)
    s = await db.stats_summary(owner_id, since)
    morn = await db.get_morning(owner_id, today)
    user = await db.get_user(owner_id)
    days_in = (today - user["start_date"]).days + 1

    weight_line = f"⚖️ Вес сегодня: {morn['weight_kg']} кг\n" if morn and morn["weight_kg"] else ""
    sleep_line  = f"💤 Сон: {morn['sleep_hours']} ч\n" if morn and morn["sleep_hours"] else ""

    text = (
        f"<b>📈 Статистика (14 дней)</b>\n\n"
        f"📅 День программы: <b>{days_in}</b>\n"
        f"✅ Закрыто полностью: <b>{s.get('done',0)}</b>\n"
        f"🟡 Минимум: <b>{s.get('minimum',0)}</b>\n"
        f"❌ Пропусков: <b>{s.get('missed',0)}</b>\n"
        f"🛌 Отдых: <b>{s.get('rest',0)}</b>\n\n"
        f"🏠 Кругов всего: <b>{s.get('total_circles',0)}</b>\n"
        f"🚴 Велик всего: <b>{s.get('total_bike',0)} мин</b>\n\n"
        f"{weight_line}{sleep_line}"
    )
    kb = back_kb()
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb)


# ---------- План недели ----------
@router.callback_query(F.data == "show:week")
async def cb_week(cb: CallbackQuery, db: Database, owner_id: int, tz):
    if cb.from_user.id != owner_id:
        await cb.answer(); return
    today_d = (await db.get_user(owner_id))["start_date"]
    from ..logic import program_position
    from datetime import datetime as _dt
    week, _ = program_position(today_d, _dt.now(tz).date())

    lines = [f"<b>🗓 План — Неделя {week}</b>"]
    for wd in range(7):
        p = get_day_plan(week, wd)
        if p.rest:
            lines.append(f"\n<b>{WEEKDAY_NAMES[wd]}</b> — 🛌 отдых")
        else:
            home_str = f"{p.home.circles} кругов" if p.home else "—"
            bike_str = f"{p.outdoor.bike_min} мин" if p.outdoor else "—"
            lines.append(f"\n<b>{WEEKDAY_NAMES[wd]}</b> · {p.title}\n   🏠 {home_str}   🚴 {bike_str}")
    await cb.message.edit_text("\n".join(lines), reply_markup=back_kb())
    await cb.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery):
    await cb.answer()
