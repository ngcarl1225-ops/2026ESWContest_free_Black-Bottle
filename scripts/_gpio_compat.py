"""이 장비(Pi 5)에서 gpiozero/lgpio가 GPIO 칩을 여는 데 실패해서 우회하는 얇은 래퍼.

pip의 `lgpio` 패키지(0.2.2.0)가 이 보드의 RP1 칩(dmesg 순서상 /dev/gpiochip15로 잡힘,
gpiozero 기본 가정인 chip=4가 아님)을 여는 데 재현 가능하게 실패한다
(`lgpio.error: 'can not open gpiochip'`, chip 번호를 맞게 지정해도 동일).
반면 시스템에 설치된 libgpiod CLI(`gpioget`)는 같은 칩/라인에서 안정적으로 동작하므로,
디지털 입력 핀 읽기는 gpiozero 대신 `gpioget`을 서브프로세스로 호출해서 처리한다.
"""
from __future__ import annotations

import re
import subprocess


def rp1_chip_name() -> str:
    """gpiodetect로 'pinctrl-rp1' 라벨을 가진 gpiochip 이름을 찾는다(보드마다 번호가 다를 수 있음).
    못 찾으면 Pi 4 이하에서 흔한 gpiochip0으로 폴백."""
    try:
        out = subprocess.run(["gpiodetect"], capture_output=True, text=True, timeout=3).stdout
        for line in out.splitlines():
            m = re.match(r"(gpiochip\d+) \[pinctrl-rp1\]", line)
            if m:
                return m.group(1)
    except Exception:
        pass
    return "gpiochip0"


class DigitalPin:
    """gpiozero.DigitalInputDevice 대체품. `.is_active`만 흉내낸다(이 프로젝트에서 쓰는 전부)."""

    def __init__(self, bcm_pin: int, chip: str | None = None):
        self.chip = chip or rp1_chip_name()
        self.pin = bcm_pin

    @property
    def is_active(self) -> bool:
        try:
            out = subprocess.run(
                ["gpioget", self.chip, str(self.pin)],
                capture_output=True,
                text=True,
                timeout=2,
            )
            return out.stdout.strip() == "1"
        except Exception:
            return False
