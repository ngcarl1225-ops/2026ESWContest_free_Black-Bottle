"""화재 감지 상태 관리.

Pi 센서 모듈은 raw 값(불꽃 여부 + 온도)만 보내고, "정상 / 주의 / 경보 / 통보 / 오프라인"
판정은 전부 여기서 한다(단일 진실 공급원).

핵심 UX 규칙
------------
- 불꽃 + 고온 동시  -> ``alarm`` : N초 안에 세대에서 취소하지 않으면 ``escalated``(관리사무소 자동 통보)
- 불꽃 또는 고온 하나 -> ``warning``
- 둘 다 아님          -> ``normal``
- 마지막 보고 이후 오래 끊김 -> ``offline`` (단, 경보/통보 상태는 데이터가 끊겨도 유지)
- "오경보예요" 취소 시 쿨다운을 걸어, 남아있는 잔여 신호로 즉시 재경보되지 않게 한다.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.fire import store
from config.settings import settings

NORMAL = "normal"
WARNING = "warning"
ALARM = "alarm"
ESCALATED = "escalated"
OFFLINE = "offline"

ACK_ACTIONS = {"checking", "called_119", "resolved"}
SIM_PRESETS = {
    "warning": (True, 30.0),
    "alarm": (True, 65.0),
    "clear": (False, 22.0),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


@dataclass
class UnitState:
    unit_id: str
    label: str
    status: str = NORMAL
    flame: bool = False
    temperature: float | None = None
    last_report: datetime | None = None
    alarm_since: datetime | None = None
    escalate_at: datetime | None = None
    admin_ack: str | None = None            # checking | called_119 | None
    muted_until: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "unit_id": self.unit_id,
            "label": self.label,
            "status": self.status,
            "flame": self.flame,
            "temperature": self.temperature,
            "last_report": _iso(self.last_report),
            "alarm_since": _iso(self.alarm_since),
            "escalate_at": _iso(self.escalate_at),
            "admin_ack": self.admin_ack,
        }


class FireManager:
    def __init__(self) -> None:
        self._units: dict[str, UnitState] = {}
        self._subscribers: set[asyncio.Queue] = set()
        self._escalation_tasks: dict[str, asyncio.Task] = {}
        self._offline_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._seed_units()

    def _seed_units(self) -> None:
        # 단지 구조(동 x 층 x 층당세대)로 자동 생성. 호수는 "층*100 + 라인" 규칙(예: 3층 2호 -> 302호).
        buildings = [b.strip() for b in (settings.fire_buildings or "").split(",") if b.strip()]
        for building in buildings:
            for floor in range(1, settings.fire_floors + 1):
                for line in range(1, settings.fire_units_per_floor + 1):
                    unit_no = floor * 100 + line
                    uid = f"{building}-{unit_no}"
                    self._units[uid] = UnitState(unit_id=uid, label=f"{building}동 {unit_no}호")

        # 자동 생성 외에 개별로 추가/덮어쓸 세대.
        for chunk in (settings.fire_units or "").split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            uid, _, label = chunk.partition("|")
            uid = uid.strip()
            if uid:
                self._units[uid] = UnitState(unit_id=uid, label=label.strip() or uid)

    # ---------- 앱 수명주기 ----------
    def start(self) -> None:
        if self._offline_task is None:
            self._offline_task = asyncio.create_task(self._offline_loop())

    async def stop(self) -> None:
        if self._offline_task:
            self._offline_task.cancel()
            self._offline_task = None
        for task in list(self._escalation_tasks.values()):
            task.cancel()
        self._escalation_tasks.clear()

    # ---------- SSE 구독 ----------
    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=32)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def _publish(self) -> None:
        payload = self.snapshot()
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass  # 느린 구독자는 다음 갱신에서 따라잡는다

    # ---------- 스냅샷 ----------
    def snapshot(self) -> dict:
        return {
            "units": [u.to_dict() for u in self._units.values()],
            "server_time": _iso(_now()),
        }

    def unit_snapshot(self, unit_id: str) -> dict:
        unit = self._units.get(unit_id)
        return {
            "unit": unit.to_dict() if unit else None,
            "server_time": _iso(_now()),
        }

    # ---------- 상태 변경 ----------
    def _get_or_create(self, unit_id: str, label: str | None) -> UnitState:
        unit = self._units.get(unit_id)
        if unit is None:
            unit = UnitState(unit_id=unit_id, label=label or unit_id)
            self._units[unit_id] = unit
        elif label and unit.label == unit.unit_id:
            unit.label = label
        return unit

    async def report(
        self,
        unit_id: str,
        flame: bool,
        temperature: float | None,
        label: str | None = None,
    ) -> UnitState:
        async with self._lock:
            unit = self._get_or_create(unit_id, label)
            unit.flame = flame
            unit.temperature = temperature
            unit.last_report = _now()
            self._recompute(unit)
            self._publish()
            return unit

    async def cancel(self, unit_id: str) -> UnitState | None:
        """세대의 '오경보예요' 버튼."""
        async with self._lock:
            unit = self._units.get(unit_id)
            if unit is None:
                return None
            self._mute_and_clear(unit)
            store.log_event("cancelled", unit)
            self._publish()
            return unit

    async def ack(self, unit_id: str, action: str) -> UnitState | None:
        """관리사무소 조치: checking / called_119 / resolved."""
        if action not in ACK_ACTIONS:
            return None
        async with self._lock:
            unit = self._units.get(unit_id)
            if unit is None:
                return None
            if action == "resolved":
                self._mute_and_clear(unit)
            else:
                unit.admin_ack = action
            store.log_event(f"ack:{action}", unit)
            self._publish()
            return unit

    async def simulate(self, unit_id: str, scenario: str, label: str | None = None) -> UnitState | None:
        """발표 데모용 가짜 트리거."""
        preset = SIM_PRESETS.get(scenario)
        if preset is None:
            return None
        flame, temp = preset
        if scenario == "clear":
            async with self._lock:
                unit = self._units.get(unit_id)
                if unit:
                    self._mute_and_clear(unit)
        return await self.report(unit_id, flame, temp, label=label)

    # ---------- 내부 로직 ----------
    def _mute_and_clear(self, unit: UnitState) -> None:
        unit.muted_until = _now() + timedelta(seconds=settings.fire_cancel_cooldown_seconds)
        unit.status = NORMAL
        unit.alarm_since = None
        unit.escalate_at = None
        unit.admin_ack = None
        self._cancel_escalation(unit.unit_id)

    def _recompute(self, unit: UnitState) -> None:
        now = _now()
        prev = unit.status

        muted = unit.muted_until is not None and now < unit.muted_until
        hot = unit.temperature is not None and unit.temperature >= settings.fire_temp_threshold_c
        stale = (
            unit.last_report is not None
            and (now - unit.last_report).total_seconds() > settings.fire_offline_seconds
        )

        if muted:
            # 세대/관리사무소가 취소·종료한 직후. 잔여 신호로 재경보하지 않는다.
            new = NORMAL
        elif stale:
            # 센서와 연결이 끊기면 과거 값으로 새 경보를 울리지 않는다.
            # 단, 이미 진행 중인 경보/통보는 계속 표시(센서가 불에 손상됐을 수도 있다).
            new = prev if prev in (ALARM, ESCALATED) else OFFLINE
        elif unit.flame and hot:
            new = ALARM
        elif unit.flame or hot:
            new = WARNING
        else:
            new = NORMAL

        # 이미 통보된 건은 잠깐 값이 정상으로 보여도 상황종료 전까지 유지.
        if prev == ESCALATED and not muted:
            new = ESCALATED

        if new == prev:
            return

        unit.status = new
        self._on_transition(unit, new)

    def _on_transition(self, unit: UnitState, new: str) -> None:
        if new == ALARM:
            unit.alarm_since = _now()
            unit.escalate_at = unit.alarm_since + timedelta(seconds=settings.fire_escalation_seconds)
            self._schedule_escalation(unit.unit_id)
        else:
            unit.escalate_at = None
            self._cancel_escalation(unit.unit_id)
            if new != ESCALATED:
                unit.alarm_since = None
                unit.admin_ack = None
        store.log_event(f"status:{new}", unit)

    def _schedule_escalation(self, unit_id: str) -> None:
        self._cancel_escalation(unit_id)
        self._escalation_tasks[unit_id] = asyncio.create_task(self._escalate_after(unit_id))

    def _cancel_escalation(self, unit_id: str) -> None:
        task = self._escalation_tasks.pop(unit_id, None)
        if task:
            task.cancel()

    async def _escalate_after(self, unit_id: str) -> None:
        try:
            await asyncio.sleep(settings.fire_escalation_seconds)
        except asyncio.CancelledError:
            return
        async with self._lock:
            unit = self._units.get(unit_id)
            if unit and unit.status == ALARM:
                unit.status = ESCALATED
                unit.escalate_at = None
                store.log_event("status:escalated", unit)
                self._publish()
        self._escalation_tasks.pop(unit_id, None)

    async def _offline_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(5)
                async with self._lock:
                    changed = False
                    for unit in self._units.values():
                        before = unit.status
                        self._recompute(unit)
                        changed = changed or unit.status != before
                    if changed:
                        self._publish()
            except asyncio.CancelledError:
                return
            except Exception:
                await asyncio.sleep(5)  # 데모 중 백그라운드 태스크가 죽지 않도록 방어


manager = FireManager()
