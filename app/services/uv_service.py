from datetime import datetime, timedelta

import httpx

from config.settings import settings

# 생활기상지수 조회서비스(3.0) 자외선지수 - 활용신청 상세기능정보 기준 실제 엔드포인트(V5)
BASE_URL = "https://apis.data.go.kr/1360000/LivingWthrIdxServiceV5/getUVIdxV5"

UV_GRADE_MAP = {
    range(0, 3): "낮음",
    range(3, 6): "보통",
    range(6, 8): "높음",
    range(8, 11): "매우높음",
}


def _grade_from_value(value: int) -> str:
    for r, label in UV_GRADE_MAP.items():
        if value in r:
            return label
    return "위험"


def _mock_uv() -> dict:
    return {"mock": True, "uv_index": 7, "grade": _grade_from_value(7)}


def _latest_report_time(now: datetime | None = None) -> str:
    # 생활기상지수는 하루 2~3회 발표. 가장 단순하게 오늘 06시 발표본을 기준으로 요청.
    now = now or datetime.now()
    base = now.replace(hour=6, minute=0, second=0, microsecond=0)
    if now < base:
        base -= timedelta(days=1)
    return base.strftime("%Y%m%d%H")


async def get_uv_index() -> dict:
    if settings.use_mock_data or not settings.kma_service_key:
        return _mock_uv()

    params = {
        "serviceKey": settings.kma_service_key,
        "dataType": "JSON",
        "areaNo": settings.kma_uv_area_no,
        "time": _latest_report_time(),
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        item = data["response"]["body"]["items"]["item"][0]
        # 응답 필드명은 시간대별 지수(h0, h3, h6 ...)로 내려오므로 가장 이른 시각값 사용
        value = int(item.get("h0", 0))

        return {"mock": False, "uv_index": value, "grade": _grade_from_value(value)}
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        print(f"[uv_service] API call failed, falling back to mock: {e}")
        return _mock_uv()
