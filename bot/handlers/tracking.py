"""Утренний трекинг: вес, сон, настроение, усталость."""
from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ..db import Database
from ..keyboards import back_kb, scale_kb
from ..texts import ASK_FATIGUE, ASK_MOOD, ASK_SLEEP, ASK_WEIGHT, BAD_NUMBER, CANCELLED

router = Router(name="tracking")


class Track(StatesGroup):
    weight = State()
    sleep = State()
    mood = State()


def _parse_float(text: str) -> float | None:
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


# ---------- /weight 78.5 ----------
@router.message(Command("weight"))
async def cmd_weight(message: Message, db: Database, owner_id: int, tz):
    if message.from_user.id != owner_id: return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(ASK_WEIGHT); return
    val = _parse_float(parts[1])
    if val is None:
        await message.answer(BAD_NUMBER); return
    await db.upsert_morning(owner_id, datetime.now(tz).date(), weight=val)
    await message.answer(f"⚖️ Вес записан: <b>{val} кг</b>")


@router.message(Command("sleep"))
async def cmd_sleep(message: Message, db: Database, owner_id: int, tz):
    if message.from_user.id != owner_id: return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(ASK_SLEEP); return
    val = _parse_float(parts[1])
    if val is None:
        await message.answer(BAD_NUMBER); return
    await db.upsert_morning(owner_id, datetime.now(tz).date(), sleep=val)
    await message.answer(f"💤 Сон записан: <b>{val} ч</b>")


# ---------- Меню «Утро» ----------
@router.callback_query(F.data == "morning:start")
@router.message(F.text == "🌅 Утро")
async def morning_start(event, state: FSMContext, owner_id: int):
    uid = event.from_user.id
    if uid != owner_id:
        if isinstance(event, CallbackQuery): await event.answer()
        return
    await state.set_state(Track.weight)
    text = ASK_WEIGHT
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=back_kb())
        await event.answer()
    else:
        await event.answer(text, reply_markup=back_kb())


@router.message(Track.weight)
async def st_weight(message: Message, state: FSMContext, db: Database, owner_id: int, tz):
    if message.from_user.id != owner_id: return
    val = _parse_float(message.text or "")
    if val is None:
        await message.answer(BAD_NUMBER); return
    await db.upsert_morning(owner_id, datetime.now(tz).date(), weight=val)
    await state.set_state(Track.sleep)
    await message.answer(ASK_SLEEP)


@router.message(Track.sleep)
async def st_sleep(message: Message, state: FSMContext, db: Database, owner_id: int, tz):
    if message.from_user.id != owner_id: return
    val = _parse_float(message.text or "")
    if val is None:
        await message.answer(BAD_NUMBER); return
    await db.upsert_morning(owner_id, datetime.now(tz).date(), sleep=val)
    await state.set_state(Track.mood)
    await message.answer(ASK_MOOD, reply_markup=scale_kb("mood"))


# ---------- Mood/fatigue ----------
@router.callback_query(F.data == "mood:start")
async def mood_start(cb: CallbackQuery, state: FSMContext, owner_id: int):
    if cb.from_user.id != owner_id:
        await cb.answer(); return
    await state.clear()
    await cb.message.edit_text(ASK_MOOD, reply_markup=scale_kb("mood"))
    await cb.answer()


@router.callback_query(F.data.startswith("mood:"))
async def mood_pick(cb: CallbackQuery, state: FSMContext, db: Database, owner_id: int, tz):
    if cb.from_user.id != owner_id:
        await cb.answer(); return
    val_str = cb.data.split(":")[1]
    if not val_str.isdigit():
        await cb.answer(); return
    val = int(val_str)
    await db.upsert_morning(owner_id, datetime.now(tz).date(), mood=val)
    await cb.message.edit_text(ASK_FATIGUE, reply_markup=scale_kb("fatigue"))
    await cb.answer(f"Настроение: {val}")


@router.callback_query(F.data.startswith("fatigue:"))
async def fatigue_pick(cb: CallbackQuery, state: FSMContext, db: Database, owner_id: int, tz):
    if cb.from_user.id != owner_id:
        await cb.answer(); return
    val = int(cb.data.split(":")[1])
    await db.upsert_morning(owner_id, datetime.now(tz).date(), fatigue=val)
    await state.clear()
    await cb.message.edit_text(f"✅ Записано. Усталость: <b>{val}</b>", reply_markup=back_kb())
    await cb.answer()


@router.callback_query(F.data == "cancel")
async def cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text(CANCELLED, reply_markup=back_kb())
    await cb.answer()
