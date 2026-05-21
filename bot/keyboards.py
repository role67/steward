"""Inline-клавиатуры."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

# ---------- Дейлики ----------
def daily_kb(home: bool, bike: bool, pullups: bool, is_rest: bool, status: str = "pending") -> InlineKeyboardMarkup:
    if is_rest:
        rows = [[InlineKeyboardButton(text="🛌 Воскресенье — отдых", callback_data="noop")]]
        rows.append([
            InlineKeyboardButton(text="🔄 Обновить", callback_data="daily:refresh"),
            InlineKeyboardButton(text="📊 Меню", callback_data="menu"),
        ])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def mark(b: bool) -> str: return "✅" if b else "⬜"

    rows = [
        [InlineKeyboardButton(text=f"{mark(home)} Дом",       callback_data="toggle:home")],
        [InlineKeyboardButton(text=f"{mark(bike)} Велик",     callback_data="toggle:bike")],
        [InlineKeyboardButton(text=f"{mark(pullups)} Турник", callback_data="toggle:pullups")],
        [
            InlineKeyboardButton(text="🏁 Закрыть день",   callback_data="daily:done"),
            InlineKeyboardButton(text="🟡 Минимум",        callback_data="daily:minimum"),
        ],
        [
            InlineKeyboardButton(text="❌ Пропуск",        callback_data="daily:missed"),
            InlineKeyboardButton(text="🔄 Обновить",       callback_data="daily:refresh"),
        ],
    ]
    if status != "pending":
        label_map = {"done": "закрыт", "minimum": "минимум", "missed": "пропуск"}
        cur = label_map.get(status, status)
        rows.append([InlineKeyboardButton(
            text=f"↩ Открыть заново (сейчас: {cur})",
            callback_data="daily:reopen",
        )])
    rows.append([InlineKeyboardButton(text="📊 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- Клавиатура напоминания ----------
def reminder_kb(key: str, postponable: bool, current_offset: int) -> InlineKeyboardMarkup | None:
    """Кнопки на самом сообщении-напоминании.
    +30 / +60 — сдвинуть остаток дня. ↩ Сбросить — если оффсет уже есть.
    """
    if not postponable:
        return None
    rows = [[
        InlineKeyboardButton(text="⏰ +30 мин", callback_data=f"postpone:30:{key}"),
        InlineKeyboardButton(text="⏰ +60 мин", callback_data=f"postpone:60:{key}"),
    ]]
    if current_offset > 0:
        rows.append([InlineKeyboardButton(
            text=f"↩ Сбросить сдвиг (+{current_offset} мин)",
            callback_data="postpone:reset",
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- Главное меню ----------
def main_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📅 Сегодня",     callback_data="show:today")],
        [InlineKeyboardButton(text="📈 Статистика",  callback_data="show:stats")],
        [InlineKeyboardButton(text="🌅 Утро (вес/сон)", callback_data="morning:start")],
        [InlineKeyboardButton(text="😴 Настроение/усталость", callback_data="mood:start")],
        [InlineKeyboardButton(text="🗓 План недели", callback_data="show:week")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- Шкала 1..5 для настроения/усталости ----------
def scale_kb(prefix: str) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(text=str(i), callback_data=f"{prefix}:{i}") for i in range(1, 6)]
    return InlineKeyboardMarkup(inline_keyboard=[row, [InlineKeyboardButton(text="Отмена", callback_data="cancel")]])


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="menu")]])


# ---------- Reply-клавиатура (стартовая) ----------
def main_reply_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Сегодня"), KeyboardButton(text="📈 Статистика")],
            [KeyboardButton(text="🌅 Утро"), KeyboardButton(text="🗓 Меню")],
        ],
        resize_keyboard=True,
    )
