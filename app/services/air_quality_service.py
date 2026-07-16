import httpx

from config.settings import settings

BASE_URL = "https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty"

# 통합대기환경지수(khaiGrade) / 개별 오염물질 등급 공통 스케일: 1 좋음, 2 보통, 3 나쁨, 4 매우나쁨
KHAI_GRADE_MAP = {"1": "좋음", "2": "보통", "3": "나쁨", "4": "매우나쁨"}


def _mock_air_quality() -> dict:
    return {
        "mock": True,
        "pm10": 45,
        "pm25": 22,
        "khai_grade": "보통",
    }


def _parse_measurement(value) -> int | None:
    # 통신장애 등으로 "-"가 오는 경우가 흔해서 숫자로 못 바꾸면 None 처리
    if value is None:
        return None
    value = str(value).strip()
    if not value or value == "-":
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _resolve_grade(item: dict) -> str:
    khai_grade = KHAI_GRADE_MAP.get(item.get("khaiGrade"))
    if khai_grade:
        return khai_grade

    # 실시간 응답은 통합대기환경지수(khaiGrade)가 비어있는 경우가 잦다.
    # 이땐 개별 오염물질의 실시간 등급 중 더 나쁜 쪽으로 대체 계산한다.
    candidate_grades = [
        int(item[key])
        for key in ("pm10Grade1h", "pm25Grade1h", "pm10Grade", "pm25Grade")
        if item.get(key) in KHAI_GRADE_MAP
    ]
    if candidate_grades:
        return KHAI_GRADE_MAP[str(max(candidate_grades))]
    return "정보없음"


async def get_air_quality() -> dict:
    if settings.use_mock_data or not settings.airkorea_service_key:
        return _mock_air_quality()

    params = {
        "serviceKey": settings.airkorea_service_key,
        "returnType": "json",
        "stationName": settings.airkorea_station_name,
        "dataTerm": "DAILY",
        "pageNo": 1,
        "numOfRows": 5,
        "ver": "1.3",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        items = data["response"]["body"]["items"]

        # 통신장애로 가장 최근 시간대의 PM10/PM2.5가 비어있는 경우가 있어,
        # 값이 실제로 있는 가장 최근 항목을 찾아서 사용한다.
        pm10 = pm25 = None
        chosen = None
        for item in items:
            pm10 = _parse_measurement(item.get("pm10Value"))
            pm25 = _parse_measurement(item.get("pm25Value"))
            if pm10 is not None or pm25 is not None:
                chosen = item
                break

        if chosen is None:
            raise ValueError("최근 항목에 PM10/PM2.5 값이 전부 없음")

        return {
            "mock": False,
            "pm10": pm10 or 0,
            "pm25": pm25 or 0,
            "khai_grade": _resolve_grade(chosen),
        }
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        print(f"[air_quality_service] API call failed, falling back to mock: {e}")
        return _mock_air_quality()
