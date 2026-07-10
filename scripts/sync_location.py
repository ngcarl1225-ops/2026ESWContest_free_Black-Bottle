import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.geo_service import detect_ip_location

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _update_env_var(content: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^{key}=.*$", re.MULTILINE)
    line = f"{key}={value}"
    if pattern.search(content):
        return pattern.sub(line, content)
    return content.rstrip("\n") + f"\n{line}\n"


async def main():
    loc = await detect_ip_location()

    print(f"감지된 위치: {loc['sido']} {loc['city']} (위도 {loc['lat']}, 경도 {loc['lon']})")
    print(f"기상청 격자좌표: NX={loc['nx']}, NY={loc['ny']}")
    print(f"생활기상지수 구역코드(추정): {loc['uv_area_no']}")
    print(f"에어코리아 측정소명(추정): {loc['city']}")

    if loc["uv_area_no"] is None:
        print("경고: 시도명을 구역코드 표에서 찾지 못했습니다. KMA_UV_AREA_NO는 직접 확인해서 넣어주세요.")

    content = ENV_PATH.read_text(encoding="utf-8")
    content = _update_env_var(content, "NX", str(loc["nx"]))
    content = _update_env_var(content, "NY", str(loc["ny"]))
    content = _update_env_var(content, "AIRKOREA_STATION_NAME", loc["city"])
    if loc["uv_area_no"]:
        content = _update_env_var(content, "KMA_UV_AREA_NO", loc["uv_area_no"])
    ENV_PATH.write_text(content, encoding="utf-8")

    print(f"\n.env 업데이트 완료: {ENV_PATH}")
    print("주의: IP 기반 위치는 시/구 단위 근사치입니다. AIRKOREA_STATION_NAME은 실제 에어코리아 측정소 목록과 이름이 다를 수 있으니 확인해주세요.")


if __name__ == "__main__":
    asyncio.run(main())
