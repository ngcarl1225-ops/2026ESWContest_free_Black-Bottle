"""라즈베리파이 화재 감지 센서 모듈 -> 백엔드 보고.

불꽃 센서(C57 DO)와 DS18B20 온도를 매초 읽어 백엔드로 POST 한다.
"정상 / 주의 / 경보 / 통보" 판정은 백엔드가 하므로 이 스크립트는 raw 값만 보낸다.
백엔드 연결이 끊겨도 죽지 않고 계속 재시도한다(백엔드는 보고 끊김을 오프라인으로 표시).

환경변수 (.env 또는 셸):
    FIRE_BACKEND_URL   기본 http://localhost:8000
    FIRE_UNIT_ID       기본 101-1203        (관리사무소가 식별하는 세대 id)
    FIRE_UNIT_LABEL    기본 없음            (예: "101동 1203호")
    FIRE_TOKEN         기본 없음            (백엔드 FIRE_TOKEN 과 일치해야 함)
    FIRE_FLAME_GPIO    기본 4
    FIRE_REPORT_INTERVAL  기본 1.0 (초)
"""
import glob
import os
from time import sleep

import httpx
from gpiozero import DigitalInputDevice

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

BACKEND_URL = os.environ.get("FIRE_BACKEND_URL", "http://localhost:8000").rstrip("/")
UNIT_ID = os.environ.get("FIRE_UNIT_ID", "101-1203")
UNIT_LABEL = os.environ.get("FIRE_UNIT_LABEL") or None
TOKEN = os.environ.get("FIRE_TOKEN", "")
FLAME_GPIO = int(os.environ.get("FIRE_FLAME_GPIO", "4"))
INTERVAL = float(os.environ.get("FIRE_REPORT_INTERVAL", "1.0"))

REPORT_ENDPOINT = f"{BACKEND_URL}/api/fire/report"

# 불꽃 센서(C57) DO 핀
flame_sensor = DigitalInputDevice(FLAME_GPIO)


def find_ds18b20_path():
    # DS18B20은 1-Wire 버스에 연결되면 커널이 /sys/bus/w1/devices/28-* 로 자동 등록한다.
    matches = glob.glob("/sys/bus/w1/devices/28-*/w1_slave")
    if not matches:
        raise RuntimeError("DS18B20을 찾을 수 없습니다 (/sys/bus/w1/devices/28-* 없음)")
    return matches[0]


def read_temperature_c(device_path):
    with open(device_path) as f:
        lines = f.readlines()

    if not lines[0].strip().endswith("YES"):
        return None  # CRC 실패, 이번 측정은 건너뜀

    temp_pos = lines[1].find("t=")
    if temp_pos == -1:
        return None

    return float(lines[1][temp_pos + 2:]) / 1000.0


def main():
    ds18b20_path = find_ds18b20_path()
    print(f"화재 감지 시스템 작동 시작... (세대 {UNIT_ID}, 백엔드 {REPORT_ENDPOINT})")

    headers = {"X-Fire-Token": TOKEN} if TOKEN else {}
    last_temp = None
    warned_offline = False

    with httpx.Client(timeout=5.0) as client:
        while True:
            flame_detected = bool(flame_sensor.is_active)
            temperature = read_temperature_c(ds18b20_path)
            if temperature is None:
                temperature = last_temp  # CRC 실패 시 직전 값 유지
            else:
                last_temp = temperature

            temp_str = f"{temperature:.1f}°C" if temperature is not None else "N/A"
            payload = {
                "unit_id": UNIT_ID,
                "flame": flame_detected,
                "temperature": temperature,
                "label": UNIT_LABEL,
            }

            try:
                resp = client.post(REPORT_ENDPOINT, json=payload, headers=headers)
                resp.raise_for_status()
                status = resp.json().get("unit", {}).get("status", "?")
                print(f"불꽃={'감지' if flame_detected else '정상'} 온도={temp_str} -> 서버상태={status}")
                warned_offline = False
            except Exception as exc:
                if not warned_offline:
                    print(f"[경고] 백엔드 보고 실패: {exc} (계속 재시도)")
                    warned_offline = True

            sleep(INTERVAL)


if __name__ == "__main__":
    main()
