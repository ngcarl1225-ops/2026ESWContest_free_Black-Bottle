import glob
from time import sleep

from gpiozero import DigitalInputDevice

# 불꽃 센서(C57) DO 핀 = GPIO4
flame_sensor = DigitalInputDevice(4)

# DS18B20은 1-Wire 버스(GPIO17)에 연결되어 있고, 커널이 /sys/bus/w1/devices/28-*
# 경로로 자동 등록해준다. 센서 ID는 하드웨어마다 다르므로 매번 탐색한다.
FIRE_TEMP_THRESHOLD_C = 50.0


def find_ds18b20_path():
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


ds18b20_path = find_ds18b20_path()
print(f"화재 감지 시스템 작동 시작... (DS18B20: {ds18b20_path})")

while True:
    flame_detected = flame_sensor.is_active
    temperature = read_temperature_c(ds18b20_path)

    if temperature is None:
        print("DS18B20 읽기 실패 (CRC 오류), 재시도...")
        sleep(1)
        continue

    fire_alert = flame_detected and temperature >= FIRE_TEMP_THRESHOLD_C

    status = f"불꽃={'감지' if flame_detected else '정상'} 온도={temperature:.1f}°C"
    if fire_alert:
        print(f"🔥🔥 화재 경보! 불꽃과 고온이 동시에 감지되었습니다. ({status})")
    else:
        print(status)

    sleep(1)
