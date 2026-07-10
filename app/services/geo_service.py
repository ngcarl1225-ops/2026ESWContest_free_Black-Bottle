import math

import httpx

# 기상청 격자좌표 변환 공식 (Lambert Conformal Conic, 기상청 공식 배포 파라미터)
_RE = 6371.00877  # 지구 반경(km)
_GRID = 5.0  # 격자 간격(km)
_SLAT1 = 30.0  # 투영 위도1
_SLAT2 = 60.0  # 투영 위도2
_OLON = 126.0  # 기준점 경도
_OLAT = 38.0  # 기준점 위도
_XO = 43  # 기준점 X좌표
_YO = 136  # 기준점 Y좌표

# 생활기상지수 구역코드는 행정표준코드관리시스템의 시도코드(2자리) + 00000000 관례를 따름.
# Nominatim이 주는 ISO3166-2 코드(예: "KR-11")의 숫자부와 대부분 일치하지만,
# 세종(ISO 50 -> 국내 36)과 제주(ISO 49 -> 국내 50)만 다르므로 별도 매핑함.
# 실제 값과 다를 수 있으니 첫 실행 후 반드시 확인할 것.
_ISO_TO_SIDO_CODE = {
    "KR-11": "11",  # 서울
    "KR-26": "26",  # 부산
    "KR-27": "27",  # 대구
    "KR-28": "28",  # 인천
    "KR-29": "29",  # 광주
    "KR-30": "30",  # 대전
    "KR-31": "31",  # 울산
    "KR-41": "41",  # 경기
    "KR-42": "42",  # 강원
    "KR-43": "43",  # 충북
    "KR-44": "44",  # 충남
    "KR-45": "45",  # 전북
    "KR-46": "46",  # 전남
    "KR-47": "47",  # 경북
    "KR-48": "48",  # 경남
    "KR-49": "50",  # 제주 (ISO 49 -> 국내 표준코드 50)
    "KR-50": "36",  # 세종 (ISO 50 -> 국내 표준코드 36)
}


def latlon_to_grid(lat: float, lon: float) -> tuple[int, int]:
    deg_rad = math.pi / 180.0
    re = _RE / _GRID
    slat1 = _SLAT1 * deg_rad
    slat2 = _SLAT2 * deg_rad
    olon = _OLON * deg_rad
    olat = _OLAT * deg_rad

    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = math.pow(sf, sn) * math.cos(slat1) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / math.pow(ro, sn)

    ra = math.tan(math.pi * 0.25 + lat * deg_rad * 0.5)
    ra = re * sf / math.pow(ra, sn)
    theta = lon * deg_rad - olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn

    nx = int(ra * math.sin(theta) + _XO + 0.5)
    ny = int(ro - ra * math.cos(theta) + _YO + 0.5)
    return nx, ny


async def _detect_lat_lon() -> tuple[float, float]:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get("http://ip-api.com/json/")
        resp.raise_for_status()
        data = resp.json()

    if data.get("status") != "success":
        raise RuntimeError(f"IP 위치 감지 실패: {data.get('message')}")

    return data["lat"], data["lon"]


async def _reverse_geocode_ko(lat: float, lon: float) -> dict:
    # ip-api는 지역명을 영어로만 제공해 에어코리아 측정소명(한글)과 매칭이 안 되므로
    # Nominatim(OSM) 역지오코딩으로 한글 주소를 별도로 받아온다.
    headers = {"User-Agent": "entrance-display-app/1.0 (personal home project)"}
    params = {"lat": lat, "lon": lon, "format": "json", "accept-language": "ko", "zoom": 12}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get("https://nominatim.openstreetmap.org/reverse", params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    return data.get("address", {})


async def detect_ip_location() -> dict:
    lat, lon = await _detect_lat_lon()
    nx, ny = latlon_to_grid(lat, lon)

    address = await _reverse_geocode_ko(lat, lon)
    sido = address.get("state") or address.get("city") or ""
    district = (
        address.get("borough")
        or address.get("city_district")
        or address.get("county")
        or address.get("suburb")
        or ""
    )

    iso_code = address.get("ISO3166-2-lvl4", "")
    sido_code = _ISO_TO_SIDO_CODE.get(iso_code)
    uv_area_no = f"{sido_code}00000000" if sido_code else None

    return {
        "lat": lat,
        "lon": lon,
        "sido": sido,
        "city": district,
        "nx": nx,
        "ny": ny,
        "uv_area_no": uv_area_no,
    }
