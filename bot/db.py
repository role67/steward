"""Подключение к Postgres (Neon) и базовые операции."""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

import asyncpg

log = logging.getLogger(__name__)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id     BIGINT PRIMARY KEY,
    tz          TEXT NOT NULL DEFAULT 'Europe/Moscow',
    start_date  DATE NOT NULL DEFAULT CURRENT_DATE,   -- старт программы, неделя считается от него
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Один дневник на день: статус, какие пункты сделаны, минимум/полный/пропуск
CREATE TABLE IF NOT EXISTS daily_logs (
    user_id      BIGINT  NOT NULL,
    log_date     DATE    NOT NULL,
    week_number  INT     NOT NULL,         -- 1 или 2 (циклично)
    weekday      INT     NOT NULL,         -- 0..6
    home_done    BOOL    NOT NULL DEFAULT FALSE,
    bike_done    BOOL    NOT NULL DEFAULT FALSE,
    pullups_done BOOL    NOT NULL DEFAULT FALSE,
    circles      INT,                       -- сколько кругов реально сделал
    bike_minutes INT,
    negatives    INT,
    status       TEXT    NOT NULL DEFAULT 'pending', -- pending|done|minimum|missed|rest
    closed_at    TIMESTAMPTZ,
    PRIMARY KEY (user_id, log_date)
);

-- Утренний трекинг
CREATE TABLE IF NOT EXISTS morning_logs (
    user_id     BIGINT NOT NULL,
    log_date    DATE   NOT NULL,
    weight_kg   NUMERIC(5,2),
    sleep_hours NUMERIC(4,2),
    mood        INT,                  -- 1..5
    fatigue     INT,                  -- 1..5
    note        TEXT,
    PRIMARY KEY (user_id, log_date)
);

-- Дополнительные наказания, начисленные на конкретный день
CREATE TABLE IF NOT EXISTS punishments (
    id          SERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL,
    apply_date  DATE   NOT NULL,
    extra_circles INT NOT NULL DEFAULT 0,
    extra_bike   INT NOT NULL DEFAULT 0,
    reason      TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_punishments_user_date
    ON punishments(user_id, apply_date);
"""


class Database:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        # statement_cache_size=0 — для совместимости с pgbouncer/Neon pooler
        self._pool = await asyncpg.create_pool(
            self.dsn,
            min_size=1,
            max_size=5,
            statement_cache_size=0,
            command_timeout=30,
        )
        async with self._pool.acquire() as con:
            await con.execute(SCHEMA_SQL)
        log.info("Database connected and schema ensured.")

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    @property
    def pool(self) -> asyncpg.Pool:
        assert self._pool is not None, "DB not connected"
        return self._pool

    # ---------- USERS ----------
    async def ensure_user(self, user_id: int, tz: str) -> None:
        await self.pool.execute(
            "INSERT INTO users(user_id, tz) VALUES($1,$2) "
            "ON CONFLICT (user_id) DO NOTHING",
            user_id, tz,
        )

    async def get_user(self, user_id: int) -> Optional[asyncpg.Record]:
        return await self.pool.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)

    # ---------- DAILY ----------
    async def get_daily(self, user_id: int, d: date) -> Optional[asyncpg.Record]:
        return await self.pool.fetchrow(
            "SELECT * FROM daily_logs WHERE user_id=$1 AND log_date=$2",
            user_id, d,
        )

    async def upsert_daily(
        self, user_id: int, d: date, week: int, weekday: int, status: str = "pending"
    ) -> None:
        await self.pool.execute(
            """
            INSERT INTO daily_logs(user_id, log_date, week_number, weekday, status)
            VALUES($1,$2,$3,$4,$5)
            ON CONFLICT (user_id, log_date) DO NOTHING
            """,
            user_id, d, week, weekday, status,
        )

    async def set_daily_status(
        self, user_id: int, d: date, status: str,
        circles: Optional[int] = None, bike_minutes: Optional[int] = None,
        negatives: Optional[int] = None,
        home_done: Optional[bool] = None, bike_done: Optional[bool] = None,
        pullups_done: Optional[bool] = None,
    ) -> None:
        sets = ["status=$3", "closed_at=NOW()"]
        params: list = [user_id, d, status]
        idx = 4
        for col, val in [
            ("circles", circles), ("bike_minutes", bike_minutes), ("negatives", negatives),
            ("home_done", home_done), ("bike_done", bike_done), ("pullups_done", pullups_done),
        ]:
            if val is not None:
                sets.append(f"{col}=${idx}")
                params.append(val)
                idx += 1
        sql = f"UPDATE daily_logs SET {', '.join(sets)} WHERE user_id=$1 AND log_date=$2"
        await self.pool.execute(sql, *params)

    async def toggle_daily_flag(self, user_id: int, d: date, field: str) -> bool:
        """Переключить булев флаг (home_done/bike_done/pullups_done), вернуть новое значение."""
        assert field in {"home_done", "bike_done", "pullups_done"}
        row = await self.pool.fetchrow(
            f"UPDATE daily_logs SET {field} = NOT {field} "
            f"WHERE user_id=$1 AND log_date=$2 RETURNING {field}",
            user_id, d,
        )
        return bool(row[field]) if row else False

    async def recent_statuses(self, user_id: int, before: date, days: int) -> list[asyncpg.Record]:
        return await self.pool.fetch(
            """
            SELECT log_date, status FROM daily_logs
            WHERE user_id=$1 AND log_date < $2
            ORDER BY log_date DESC LIMIT $3
            """,
            user_id, before, days,
        )

    # ---------- MORNING ----------
    async def upsert_morning(
        self, user_id: int, d: date,
        weight: Optional[float] = None,
        sleep: Optional[float] = None,
        mood: Optional[int] = None,
        fatigue: Optional[int] = None,
        note: Optional[str] = None,
    ) -> None:
        await self.pool.execute(
            """
            INSERT INTO morning_logs(user_id, log_date, weight_kg, sleep_hours, mood, fatigue, note)
            VALUES($1,$2,$3,$4,$5,$6,$7)
            ON CONFLICT (user_id, log_date) DO UPDATE SET
                weight_kg   = COALESCE(EXCLUDED.weight_kg,   morning_logs.weight_kg),
                sleep_hours = COALESCE(EXCLUDED.sleep_hours, morning_logs.sleep_hours),
                mood        = COALESCE(EXCLUDED.mood,        morning_logs.mood),
                fatigue     = COALESCE(EXCLUDED.fatigue,     morning_logs.fatigue),
                note        = COALESCE(EXCLUDED.note,        morning_logs.note)
            """,
            user_id, d, weight, sleep, mood, fatigue, note,
        )

    async def get_morning(self, user_id: int, d: date) -> Optional[asyncpg.Record]:
        return await self.pool.fetchrow(
            "SELECT * FROM morning_logs WHERE user_id=$1 AND log_date=$2",
            user_id, d,
        )

    # ---------- PUNISHMENTS ----------
    async def add_punishment(
        self, user_id: int, apply_date: date,
        extra_circles: int, extra_bike: int, reason: str,
    ) -> None:
        await self.pool.execute(
            """
            INSERT INTO punishments(user_id, apply_date, extra_circles, extra_bike, reason)
            VALUES($1,$2,$3,$4,$5)
            """,
            user_id, apply_date, extra_circles, extra_bike, reason,
        )

    async def get_punishments(self, user_id: int, d: date) -> list[asyncpg.Record]:
        return await self.pool.fetch(
            "SELECT * FROM punishments WHERE user_id=$1 AND apply_date=$2",
            user_id, d,
        )

    async def has_punishment_for(self, user_id: int, apply_date: date, reason: str) -> bool:
        row = await self.pool.fetchrow(
            "SELECT 1 FROM punishments WHERE user_id=$1 AND apply_date=$2 AND reason=$3",
            user_id, apply_date, reason,
        )
        return row is not None

    # ---------- STATS ----------
    async def stats_summary(self, user_id: int, since: date) -> dict:
        row = await self.pool.fetchrow(
            """
            SELECT
              COUNT(*) FILTER (WHERE status='done')    AS done,
              COUNT(*) FILTER (WHERE status='minimum') AS minimum,
              COUNT(*) FILTER (WHERE status='missed')  AS missed,
              COUNT(*) FILTER (WHERE status='rest')    AS rest,
              COALESCE(SUM(circles),0)                  AS total_circles,
              COALESCE(SUM(bike_minutes),0)             AS total_bike
            FROM daily_logs
            WHERE user_id=$1 AND log_date >= $2
            """,
            user_id, since,
        )
        return dict(row) if row else {}
