"""화재 감지 HTTP 엔드포인트.

- Pi 센서 모듈 -> POST /api/fire/report (매초, heartbeat 겸용)
- 홈 디스플레이 -> POST /api/fire/cancel ("오경보예요"), GET /api/fire/stream?unit_id=
- 관리사무소   -> POST /api/fire/ack, GET /api/fire/units, GET /api/fire/events, GET /api/fire/stream
- 발표 데모    -> POST /api/fire/simulate (debug 모드에서만)
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.fire import store
from app.fire.state import manager
from config.settings import settings

router = APIRouter(prefix="/api/fire", tags=["fire"])


class ReportIn(BaseModel):
    unit_id: str
    flame: bool
    temperature: float | None = None
    label: str | None = None


class UnitAction(BaseModel):
    unit_id: str


class AckIn(BaseModel):
    unit_id: str
    action: str  # checking | called_119 | resolved


class SimulateIn(BaseModel):
    unit_id: str
    scenario: str  # warning | alarm | clear
    label: str | None = None


def _require_token(provided: str | None, expected: str) -> None:
    if expected and provided != expected:
        raise HTTPException(status_code=401, detail="invalid token")


@router.post("/report")
async def fire_report(body: ReportIn, x_fire_token: str | None = Header(default=None)):
    _require_token(x_fire_token, settings.fire_token)
    unit = await manager.report(body.unit_id, body.flame, body.temperature, label=body.label)
    return {"ok": True, "unit": unit.to_dict()}


@router.post("/cancel")
async def fire_cancel(body: UnitAction):
    unit = await manager.cancel(body.unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="unknown unit")
    return {"ok": True, "unit": unit.to_dict()}


@router.post("/ack")
async def fire_ack(body: AckIn, x_admin_token: str | None = Header(default=None)):
    _require_token(x_admin_token, settings.fire_admin_token)
    unit = await manager.ack(body.unit_id, body.action)
    if unit is None:
        raise HTTPException(status_code=400, detail="unknown unit or action")
    return {"ok": True, "unit": unit.to_dict()}


@router.get("/units")
async def fire_units():
    return manager.snapshot()


@router.get("/state")
async def fire_state(unit_id: str):
    return manager.unit_snapshot(unit_id)


@router.get("/events")
async def fire_events(limit: int = 100):
    return {"events": store.recent_events(limit)}


@router.post("/simulate")
async def fire_simulate(body: SimulateIn):
    if not settings.debug:
        raise HTTPException(status_code=403, detail="simulate disabled outside debug")
    unit = await manager.simulate(body.unit_id, body.scenario, label=body.label)
    if unit is None:
        raise HTTPException(status_code=400, detail="bad scenario")
    return {"ok": True, "unit": unit.to_dict()}


@router.get("/stream")
async def fire_stream(request: Request, unit_id: str | None = None):
    """Server-Sent Events. 상태가 바뀔 때마다 스냅샷을 밀어준다.

    unit_id 를 주면 해당 세대만 골라 ``{"unit": ...}`` 형태로 보낸다(홈 디스플레이용).
    없으면 전체 목록을 보낸다(관리사무소용).
    """
    queue = manager.subscribe()

    def _shape(payload: dict) -> dict:
        if not unit_id:
            return payload
        units = {u["unit_id"]: u for u in payload.get("units", [])}
        return {"unit": units.get(unit_id), "server_time": payload.get("server_time")}

    async def event_gen():
        try:
            first = manager.unit_snapshot(unit_id) if unit_id else manager.snapshot()
            yield f"data: {json.dumps(first, ensure_ascii=False)}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {json.dumps(_shape(payload), ensure_ascii=False)}\n\n"
        finally:
            manager.unsubscribe(queue)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
