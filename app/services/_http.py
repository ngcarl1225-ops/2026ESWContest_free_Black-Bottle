"""공공데이터포털 API 호출 보조.

기상청/에어코리아 API는 동시 요청이 몇 개만 겹쳐도 504/타임아웃을 자주 낸다
(실측: 6개 동시 요청 중 4개 실패). 이 프로젝트는 프론트가 새로고침할 때마다
같은 서비스 함수를 카드용/알림용으로 거의 동시에 두 번 호출하므로, 재시도와
짧은 캐시로 완화한다.
"""
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, TypeVar

import httpx

T = TypeVar("T")


async def get_json_with_retry(
    url: str,
    params: dict,
    *,
    timeout: float = 10.0,
    retries: int = 1,
    backoff_seconds: float = 0.8,
) -> dict:
    """실패 시 짧게 한 번 재시도 후 그래도 안 되면 예외를 그대로 던진다(호출부의 mock 폴백으로 이어짐)."""
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as e:
            last_error = e
            if attempt < retries:
                await asyncio.sleep(backoff_seconds)
    raise last_error


def ttl_cache(seconds: float) -> Callable[[Callable[[], Awaitable[T]]], Callable[[], Awaitable[T]]]:
    """인자 없는 async 함수용 초단기 캐시.

    카드 위젯과 알림 엔진이 같은 새로고침 주기에 같은 데이터를 거의 동시에 두 번 요청하는데,
    그 중복 호출이 외부 API를 두 번 두드리지 않도록 짧게 재사용한다(실시간성에 영향 없는 범위).
    """

    def decorator(fn: Callable[[], Awaitable[T]]) -> Callable[[], Awaitable[T]]:
        cached_value: T | None = None
        cached_at = 0.0
        lock = asyncio.Lock()

        async def wrapper() -> T:
            nonlocal cached_value, cached_at
            async with lock:
                now = time.monotonic()
                if cached_value is not None and now - cached_at < seconds:
                    return cached_value
                cached_value = await fn()
                cached_at = time.monotonic()
                return cached_value

        return wrapper

    return decorator
