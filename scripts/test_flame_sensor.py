from gpiozero import DigitalInputDevice
from time import sleep

# GPIO 17번 핀을 입력 핀으로 설정
sensor = DigitalInputDevice(17)

print("센서 작동 시작...")

n = 0

while True:
    n += 1
    if sensor.is_active:  # 센서에 신호가 들어오면
        print(f"O {n}")
    else:                 # 신호가 없으면
        print(f"X {n}")

    sleep(1)  # 1초마다 반복해서 확인