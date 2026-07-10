import httpx

from config.settings import settings

BASE_URL = "https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty"

# 통합대기환경지수(khaiGrade) 등급: 1 좋음, 2 보통, 3 나쁨, 4 매우나쁨
KHAI_GRADE_MAP = {"1": "좋음", "2": "보통", "3": "나쁨", "4": "매우나쁨"}


def _mock_air_quality() -> dict:
    return {
        "mock": True,
        "pm10": 45,
        "pm25": 22,
        "khai_grade": "보통",
    }


async def get_air_quality() -> dict:
    if settings.use_mock_data or not settings.airkorea_service_key:
        return _mock_air_quality()

    params = {
        "serviceKey": settings.airkorea_service_key,
        "returnType": "json",
        "stationName": settings.airkorea_station_name,
        "dataTerm": "DAILY",
        "pageNo": 1,
        "numOfRows": 1,
        "ver": "1.3",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        item = data["response"]["body"]["items"][0]

        return {
            "mock": False,
            "pm10": int(item.get("pm10Value", 0) or 0),
            "pm25": int(item.get("pm25Value", 0) or 0),
            "khai_grade": KHAI_GRADE_MAP.get(item.get("khaiGrade"), "정보없음"),
        }
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        print(f"[air_quality_service] API call failed, falling back to mock: {e}")
        return _mock_air_quality()
