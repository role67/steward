"""Бизнес-логика: какой сегодня день программы, наказания, рендер плана."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .db import Database
from .plan import DayPlan, WEEKDAY_NAMES, get_day_plan


# -------- Какая сегодня неделя/день --------
def program_position(start_date: date, today: date) -> tuple[int, int]:
    """Возвращает (номер_недели 1|2, weekday 0..6) циклично от start_date."""
    days = (today - start_date).days
    if days < 0:
        days = 0
    week_index = (days // 7) % 2          # 0 или 1
    weekday = today.weekday()             # 0..6 (Пн..Вс)
    return (1 if week_index == 0 else 2), weekday


# -------- Расчёт наказаний за пропуски --------
@dataclass
class PunishmentDelta:
    extra_circles: int
    extra_bike: int
    reason: str


def compute_punishment(prev_statuses: list[str], today_weekday: int) -> PunishmentDelta | None:
    """
    prev_statuses: статусы за прошлые дни в порядке от вчера к более давним
                   ('done'|'minimum'|'missed'|'rest'|'pending').
    Воскресенье (today_weekday == 6) — без наказаний.
    """
    if today_weekday == 6:
        return None
    if not prev_statuses:
        return None

    missed_states = {"missed", "pending"}
    yesterday = prev_statuses[0]
    day_before = prev_statuses[1] if len(prev_statuses) > 1 else None

    # 2 подряд И сегодня суббота — тяжёлая суббота
    if (
        today_weekday == 5
        and yesterday in missed_states
        and day_before in missed_states
        and yesterday != "rest"
        and day_before != "rest"
    ):
        return PunishmentDelta(2, 20, "2 пропуска подряд → тяжёлая суббота")

    # Один пропуск вчера
    if yesterday in missed_states and yesterday != "rest":
        return PunishmentDelta(1, 15, "Вчера пропуск → +1 круг, +15 мин велик")

    return None


# -------- Закрытие вчерашнего дня (если не отметил) --------
async def auto_close_previous_day(db: Database, user_id: int, today: date) -> None:
    """Если на вчера статус pending — помечаем missed (или rest для ВС)."""
    yesterday = today - timedelta(days=1)
    row = await db.get_daily(user_id, yesterday)
    if not row or row["status"] != "pending":
        return
    new_status = "rest" if yesterday.weekday() == 6 else "missed"
    await db.set_daily_status(user_id, yesterday, new_status)


async def apply_punishments_for_today(
    db: Database, user_id: int, today: date,
) -> PunishmentDelta | None:
    """Считает наказания на основе истории и сохраняет их (idempotent)."""
    if today.weekday() == 6:
        return None
    prev = await db.recent_statuses(user_id, before=today, days=5)
    statuses = [r["status"] for r in prev]
    delta = compute_punishment(statuses, today.weekday())
    if not delta:
        return None
    if await db.has_punishment_for(user_id, today, delta.reason):
        return delta
    await db.add_punishment(user_id, today, delta.extra_circles, delta.extra_bike, delta.reason)
    return delta


# -------- Рендер плана дня --------
def render_day_plan(today: date, week: int, plan: DayPlan, extra_circles: int = 0, extra_bike: int = 0) -> str:
    name = WEEKDAY_NAMES[today.weekday()]
    head = f"<b>{name} · Неделя {week}</b>\n<i>{plan.title}</i>\n"
    if plan.rest:
        body = ["", "🛌 <b>Полный отдых.</b>", "Можно:"]
        body += [f"• {n}" for n in plan.notes]
        return head + "\n".join(body)

    parts = [head]
    if plan.home:
        circles = plan.home.circles + extra_circles
        plus = f" <code>(+{extra_circles} за пропуск)</code>" if extra_circles else ""
        parts.append(f"\n🏠 <b>Дом — {circles} круга/-ов</b>{plus}")
        for ex in plan.home.exercises:
            parts.append(f"   • {ex}")
        parts.append(f"\n<i>Отдых: {plan.home.rest_between}; {plan.home.rest_circles}.</i>")
    if plan.outdoor:
        bike = plan.outdoor.bike_min
        plus_b = f" <code>(+{extra_bike} мин)</code>" if extra_bike else ""
        parts.append(f"\n🚴 <b>Велосипед: {bike} мин</b>{plus_b}")
        if plan.outdoor.pullup_notes:
            parts.append("🏋 <b>Турник:</b>")
            for n in plan.outdoor.pullup_notes:
                parts.append(f"   • {n}")
    if plan.notes:
        parts.append("")
        for n in plan.notes:
            parts.append(f"<i>{n}</i>")
    parts.append("\n<i>Минимум при усталости: 2 круга дома + 30 мин велика.</i>")
    return "\n".join(parts)


async def get_today_context(db: Database, user_id: int, today: date):
    """Возвращает (week, weekday, plan, extra_circles, extra_bike, daily_row)."""
    user = await db.get_user(user_id)
    if not user:
        raise RuntimeError("user not initialized")
    start = user["start_date"]
    week, weekday = program_position(start, today)
    plan = get_day_plan(week, weekday)
    status = "rest" if plan.rest else "pending"
    await db.upsert_daily(user_id, today, week, weekday, status)

    extra_c = extra_b = 0
    for p in await db.get_punishments(user_id, today):
        extra_c += p["extra_circles"]
        extra_b += p["extra_bike"]
    row = await db.get_daily(user_id, today)
    return week, weekday, plan, extra_c, extra_b, row
