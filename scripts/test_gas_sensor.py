from gpiozero import DigitalInputDevice
from time import sleep

# MQ-2 가스/연기 센서 DO 핀을 GPIO 11번에 연결
sensor = DigitalInputDevice(11)

print("가스/연기 센서 작동 시작...")

n = 0

while True:
    n += 1
    if sensor.is_active:  # 임계값을 넘는 가스/연기가 감지되면
        print(f"⚠️ 가스/연기 감지됨! {n}")
    else:                 # 정상 상태
        print(f"정상 {n}")

    sleep(1)  # 1초마다 반복해서 확인
    