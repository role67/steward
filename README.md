# Dayliki Bot

Личный Telegram-бот для дисциплины: напоминания о тренировках, дневник, наказания за пропуски.

Стек: **Python 3.11+, aiogram 3, asyncpg, APScheduler, aiohttp**.
БД: **Neon (Postgres)**. Хостинг: **Render.com**. Пинг: **UptimeRobot** (HEAD `/`).

## Что умеет

- Расписание дня (17:30 дом → 19:00 велик → 19:30 турник → 23:30 сон).
- Каждые 10 мин во время домашней тренировки — «не залипай».
- Inline-кнопки: ⬜/✅ Дом · Велик · Турник, «Закрыть день», «Минимум», «Пропуск».
- 2-недельный план (неделя 1 базовая, неделя 2 — нагрузка выше), циклично.
- **Наказания**: пропуск → +1 круг и +15 мин велика. 2 подряд → тяжёлая суббота (+2 круга, +20 мин).
- **Минимум**: 2 круга дома + 30 мин велика — лучше, чем ноль.
- **Воскресенье** — отдых, без наказаний.
- Утренний дневник: вес, сон, настроение, усталость.
- `/stats` — сводка за 14 дней.
- HTTP `HEAD /` и `GET /health` — для UptimeRobot, чтобы Render не засыпал.

## Команды

- `/start` — приветствие и меню
- `/today` — план на сегодня
- `/menu` — главное меню
- `/stats` — статистика
- `/weight 78.5` — записать вес
- `/sleep 7.5` — записать часы сна

## Локальный запуск

1. `cp .env.example .env` и заполнить.
2. `python -m venv .venv && .venv\Scripts\activate` (Windows) / `source .venv/bin/activate` (Linux/macOS).
3. `pip install -r requirements.txt`
4. `python -m bot.main`

## Neon (Postgres)

1. Создать БД на https://neon.tech (бесплатно).
2. Connection string брать **pooled** (`-pooler`), `sslmode=require`. Пример:
   `postgresql://user:pass@ep-xxx-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require`
3. Положить в `DATABASE_URL`. Схема создаётся автоматически при старте.

## Деплой на Render.com

1. Запушь репо в GitHub.
2. Render → **New → Web Service** → выбрать репо.
3. Build: `pip install -r requirements.txt`
   Start: `python -m bot.main`
   Health check: `/health`
4. В **Environment** добавить: `BOT_TOKEN`, `OWNER_ID`, `DATABASE_URL`, `TZ=Europe/Moscow`, `PUBLIC_URL=https://<service>.onrender.com`.
5. Render автоматически проставит `PORT` — бот его слушает.

(Альтернатива: использовать готовый `render.yaml`.)

## UptimeRobot

1. Создать монитор типа **HTTP(s)** → URL `https://<service>.onrender.com/`.
2. Тип запроса: **HEAD** (на этот URL бот отвечает `200`).
3. Интервал: 5 минут (для бесплатного Render это удерживает контейнер «тёплым»).

## Структура

```
bot/
  main.py          # точка входа: бот + scheduler + web
  config.py        # настройки из .env
  db.py            # asyncpg pool + схема + методы
  plan.py          # 2-недельный план + расписание напоминаний
  logic.py         # наказания, рендер дня, позиция в программе
  scheduler.py     # APScheduler-задачи
  web.py           # aiohttp с HEAD /
  keyboards.py     # inline-клавиатуры
  texts.py         # тексты
  handlers/
    __init__.py
    menu.py        # /start, /menu, /today, /stats
    workout.py     # дейлики, toggle, статусы дня
    tracking.py    # вес/сон/настроение/усталость
```

## Логика наказаний (псевдокод)

```
yesterday_status = последний статус
if today == sunday:        нет наказаний
elif today == saturday and вчера и позавчера пропуск:
    +2 круга, +20 мин велик
elif вчера пропуск:
    +1 круг, +15 мин велик
```

Наказание начисляется автоматически утром (`09:30`) и при старте домашней тренировки (`17:30`). Запись идемпотентна по причине (`reason`).
