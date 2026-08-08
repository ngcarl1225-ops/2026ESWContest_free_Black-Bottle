from gpiozero import DigitalInputDevice
from time import sleep

# 라즈베리파이 40핀 헤더에서 입력으로 쓸 수 있는 BCM 번호들
CANDIDATE_PINS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
                   16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27]

devices = {}
for pin in CANDIDATE_PINS:
    try:
        devices[pin] = DigitalInputDevice(pin)
    except Exception as e:
        print(f"BCM{pin} 열기 실패: {e}")

print("감시 시작... 가스 센서에 라이터 가스나 알코올을 가까이 대보세요.")
print("평소와 다르게 바뀌는 BCM 번호를 확인하세요 (Ctrl+C로 종료).\n")

try:
    while True:
        states = " ".join(
            f"BCM{pin}={'H' if dev.is_active else 'L'}"
            for pin, dev in devices.items()
        )
        print(states)
        sleep(1)
except KeyboardInterrupt:
    pass
