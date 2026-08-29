"""화재 이벤트 이력 저장소.

의존성을 늘리지 않도록 표준 라이브러리 sqlite3만 사용한다.
상태 전이·조치 같은 "사건"만 기록하며, 매초 들어오는 센서 보고(heartbeat)는 남기지 않는다.
기록 실패가 경보 동작 자체를 막아서는 안 되므로 모든 함수는 예외를 삼킨다.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.fire.state import UnitState

DB_PATH = Path("data/fire_events.db")


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            unit_id TEXT NOT NULL,
            label TEXT,
            event TEXT NOT NULL,
            flame INTEGER,
            temperature REAL,
            status TEXT
        )
        """
    )
    return conn


def log_event(event: str, unit: "UnitState") -> None:
    try:
        with _conn() as conn:
            conn.execute(
                "INSERT INTO events (ts, unit_id, label, event, flame, temperature, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    unit.unit_id,
                    unit.label,
                    event,
                    int(unit.flame),
                    unit.temperature,
                    unit.status,
                ),
            )
    except Exception:
        pass


def recent_events(limit: int = 100) -> list[dict]:
    try:
        with _conn() as conn:
            rows = conn.execute(
                "SELECT ts, unit_id, label, event, flame, temperature, status "
                "FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    except Exception:
        return []
    return [
        {
            "ts": r[0],
            "unit_id": r[1],
            "label": r[2],
            "event": r[3],
            "flame": bool(r[4]) if r[4] is not None else None,
            "temperature": r[5],
            "status": r[6],
        }
        for r in rows
    ]
