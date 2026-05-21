"""
Двухнедельный план тренировок.
Дни: 0=Пн, 1=Вт, 2=Ср, 3=Чт, 4=Пт, 5=Сб, 6=Вс.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

WEEKDAY_NAMES = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


@dataclass(frozen=True)
class HomeBlock:
    circles: int
    exercises: list[str]
    rest_between: str = "25 сек между упражнениями"
    rest_circles: str = "90 сек между кругами"


@dataclass(frozen=True)
class OutdoorBlock:
    bike_min: str                 # "75-90" или "90"
    pullup_notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DayPlan:
    title: str
    home: Optional[HomeBlock]
    outdoor: Optional[OutdoorBlock]
    rest: bool = False
    notes: list[str] = field(default_factory=list)


# ---------- НЕДЕЛЯ 1 ----------
WEEK_1: dict[int, DayPlan] = {
    0: DayPlan(
        title="Грудь + пресс + велик",
        home=HomeBlock(4, ["15 отжиманий", "20 пресс", "15 приседаний", "40 сек планка"]),
        outdoor=OutdoorBlock("75-90", ["вис 3×30 сек", "негативы 4×3"]),
    ),
    1: DayPlan(
        title="Турник + кардио",
        home=HomeBlock(3, ["12 отжиманий", "15 пресс", "12 приседаний"]),
        outdoor=OutdoorBlock("60-75", ["вис 3×40 сек", "негативы 5×3", "подтягивания с ногой 4×4"]),
    ),
    2: DayPlan(
        title="Жиросжигание",
        home=HomeBlock(5, ["12 отжиманий", "20 mountain climbers", "15 приседаний", "20 пресс", "35 сек планка"]),
        outdoor=OutdoorBlock("90"),
    ),
    3: DayPlan(
        title="Лёгкий день",
        home=HomeBlock(3, ["10 отжиманий", "15 пресс", "30 сек планка"]),
        outdoor=OutdoorBlock("60 (спокойный)", ["висы", "2–3 негатива"]),
    ),
    4: DayPlan(
        title="Верх тела",
        home=HomeBlock(5, ["15 широких отжиманий", "10 узких", "20 пресс", "15 приседаний"]),
        outdoor=OutdoorBlock("75", ["негативы 5×3", "подтягивания с ногой 4×4"]),
    ),
    5: DayPlan(
        title="Тяжёлый день",
        home=HomeBlock(6, ["15 отжиманий", "20 пресс", "20 приседаний", "45 сек планка", "15 выпрыгиваний"]),
        outdoor=OutdoorBlock("90-120", ["вис", "негативы", "попытки обычных подтягиваний"]),
    ),
    6: DayPlan(
        title="Воскресенье — отдых",
        home=None, outdoor=None, rest=True,
        notes=["экспандер", "прогулка", "растяжка"],
    ),
}

# ---------- НЕДЕЛЯ 2 ----------
WEEK_2: dict[int, DayPlan] = {
    0: DayPlan(
        title="Понедельник (тяжелее)",
        home=HomeBlock(5, ["18 отжиманий", "25 пресс", "18 приседаний", "45 сек планка"]),
        outdoor=OutdoorBlock("90", ["негативы 5×4"]),
    ),
    1: DayPlan(
        title="Вторник",
        home=HomeBlock(4, ["15 отжиманий", "20 пресс", "15 приседаний"]),
        outdoor=OutdoorBlock("75", ["вис", "негативы", "подтягивания с ногой"]),
    ),
    2: DayPlan(
        title="HIIT",
        home=HomeBlock(6, ["30 сек берпи", "20 mountain climbers", "15 приседаний", "15 пресс"]),
        outdoor=OutdoorBlock("60-75"),
    ),
    3: DayPlan(
        title="Лёгкий день",
        home=HomeBlock(3, ["12 отжиманий", "15 пресс", "35 сек планка"]),
        outdoor=OutdoorBlock("60", ["лёгкий турник"]),
    ),
    4: DayPlan(
        title="Пятница",
        home=HomeBlock(5, ["18 отжиманий", "12 узких", "20 пресс", "20 приседаний"]),
        outdoor=OutdoorBlock("90", ["негативы", "попытки подтягиваний"]),
    ),
    5: DayPlan(
        title="Контрольная суббота",
        home=HomeBlock(4, ["15 отжиманий", "20 пресс", "15 приседаний"]),
        outdoor=OutdoorBlock("90-120"),
        notes=["Сначала проверка: максимум отжиманий, максимум планки, попытка подтягиваний"],
    ),
    6: DayPlan(
        title="Воскресенье — отдых",
        home=None, outdoor=None, rest=True,
        notes=["экспандер", "прогулка", "растяжка"],
    ),
}

PLAN: dict[int, dict[int, DayPlan]] = {1: WEEK_1, 2: WEEK_2}


def get_day_plan(week: int, weekday: int) -> DayPlan:
    """week: 1 или 2; weekday: 0..6."""
    return PLAN[1 if week == 1 else 2][weekday]


# ---------- РАСПИСАНИЕ НАПОМИНАНИЙ ----------
# (час, минута, ключ)
@dataclass(frozen=True)
class Reminder:
    hour: int
    minute: int
    key: str
    text: str


# Базовое расписание "ранний старт" (17:30).
REMINDERS: list[Reminder] = [
    Reminder(15, 30, "food",        "🍽 Еда + отдых. Не лежать весь вечер."),
    Reminder(17, 20, "prep_home",   "⚙️ Подготовка к домашней тренировке. 10 минут."),
    Reminder(17, 30, "start_home",  "🏠 СТАРТ домашней тренировки."),
    # «Не залипай» каждые 10 минут c 17:40 до 18:10
    Reminder(17, 40, "tempo_1",     "⏱ Не залипай. Держи темп."),
    Reminder(17, 50, "tempo_2",     "⏱ Следи за отдыхом. Не зависай в телефоне."),
    Reminder(18, 0,  "tempo_3",     "⏱ Держи темп. Ты уже на половине."),
    Reminder(18, 10, "tempo_4",     "⏱ Финал кругов. Дожми."),
    Reminder(18, 20, "prep_ride",   "🚴 Подготовка к выезду. Бутылка, ключи, шлем."),
    Reminder(19, 0,  "start_bike",  "🚴 СТАРТ велосипеда."),
    Reminder(19, 30, "pullups",     "🏋 Турник. Минимум: вис + негативы."),
    Reminder(20, 30, "finish_bike", "🏁 Финиш кардио. Домой."),
    Reminder(21, 0,  "snack",       "💧 Вода. Лёгкий перекус. Без мусорной еды."),
    Reminder(22, 30, "prep_sleep",  "🌙 Подготовка ко сну."),
    Reminder(23, 0,  "shower",      "🚿 Душ."),
    Reminder(23, 30, "sleep",       "😴 СОН. Закрой ноут."),
]

# Утреннее напоминание про вес/сон
MORNING_LOG = Reminder(9, 30, "morning_log", "📊 Доброе утро. Запиши вес и сколько спал.")
