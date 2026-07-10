from collections import defaultdict
from datetime import datetime, timedelta

import httpx

from config.settings import settings

BASE_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"

# 발표시각: 매일 02,05,08,11,14,17,20,23시 (실제 제공은 각 시각 + 약 10분 후)
_BASE_TIMES = ["0200", "0500", "0800", "1100", "1400", "1700", "2000", "2300"]

PTY_MAP = {"0": "없음", "1": "비", "2": "비/눈", "3": "눈", "4": "소나기"}
SKY_MAP = {"1": "맑음", "3": "구름많음", "4": "흐림"}


def _latest_base_datetime(now: datetime | None = None) -> tuple[str, str]:
    now = now or datetime.now()
    candidates = [now.replace(hour=int(t[:2]), minute=int(t[2:]), second=0, microsecond=0) for t in _BASE_TIMES]
    valid = [c for c in candidates if now >= c + timedelta(minutes=10)]
    if valid:
        chosen = max(valid)
    else:
        # 자정 이후 02:10 이전에는 전날 23시 발표를 사용
        chosen = (now - timedelta(days=1)).replace(hour=23, minute=0, second=0, microsecond=0)
    return chosen.strftime("%Y%m%d"), chosen.strftime("%H%M")


def _mock_hourly(base_hour: int = 15) -> list[dict]:
    pattern = [
        (24.5, 30, "없음", "맑음"),
        (24.0, 30, "없음", "맑음"),
        (23.0, 40, "없음", "구름많음"),
        (22.0, 50, "없음", "흐림"),
        (21.5, 60, "비", "흐림"),
        (21.0, 60, "비", "흐림"),
    ]
    hourly = []
    for i, (temp, pop, pty, sky) in enumerate(pattern):
        hour = (base_hour + i) % 24
        hourly.append(
            {
                "time": f"{hour:02d}00",
                "temperature": temp,
                "precipitation_probability": pop,
                "precipitation_type": pty,
                "sky": sky,
            }
        )
    return hourly


def _mock_forecast() -> dict:
    return {
        "mock": True,
        "precipitation_probability": 30,
        "precipitation_type": "없음",
        "sky": "맑음",
        "temperature": 24.5,
        "humidity": 55,
        "hourly": _mock_hourly(),
    }


def _group_by_datetime(items: list[dict]) -> dict[tuple[str, str], dict[str, str]]:
    # (fcstDate, fcstTime) 튜플로 정렬해야 날짜를 넘나드는 예보에서도 시간순이 보장됨.
    # fcstTime 문자열만으로 min()을 잡으면 다른 날짜의 더 이른 시각(예: 다음날 0000)이
    # 오늘 늦은 시각보다 먼저 골라지는 버그가 생김.
    grouped: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    for item in items:
        grouped[(item["fcstDate"], item["fcstTime"])][item["category"]] = item["fcstValue"]
    return grouped


def _extract_hourly(grouped: dict[tuple[str, str], dict[str, str]], count: int = 6) -> list[dict]:
    hourly = []
    for date, time in sorted(grouped.keys())[:count]:
        values = grouped[(date, time)]
        if "TMP" not in values:
            continue
        hourly.append(
            {
                "time": time,
                "temperature": float(values["TMP"]),
                "precipitation_probability": int(values.get("POP", 0)),
                "precipitation_type": PTY_MAP.get(values.get("PTY", "0"), "없음"),
                "sky": SKY_MAP.get(values.get("SKY", "1"), "맑음"),
            }
        )
    return hourly


async def get_short_term_forecast() -> dict:
    if settings.use_mock_data or not settings.kma_service_key:
        return _mock_forecast()

    base_date, base_time = _latest_base_datetime()
    params = {
        "serviceKey": settings.kma_service_key,
        "dataType": "JSON",
        "numOfRows": 350,
        "pageNo": 1,
        "base_date": base_date,
        "base_time": base_time,
        "nx": settings.nx,
        "ny": settings.ny,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        items = data["response"]["body"]["items"]["item"]

        # (fcstDate, fcstTime) 기준 시간순 정렬 후 가장 이른 시각의 값을 "현재" 값으로 사용
        grouped = _group_by_datetime(items)
        earliest_key = min(grouped.keys())
        values = grouped[earliest_key]

        return {
            "mock": False,
            "precipitation_probability": int(values.get("POP", 0)),
            "precipitation_type": PTY_MAP.get(values.get("PTY", "0"), "없음"),
            "sky": SKY_MAP.get(values.get("SKY", "1"), "맑음"),
            "temperature": float(values.get("TMP", 0)),
            "humidity": int(values.get("REH", 0)),
            "hourly": _extract_hourly(grouped),
        }
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        print(f"[weather_service] API call failed, falling back to mock: {e}")
        return _mock_forecast()
