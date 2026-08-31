# 현관 스마트 비서 디스플레이 (Entrance Assistant Display)

라즈베리파이 + 모니터로 현관 앞에 설치하는 개인 맞춤형 정보 비서.
날씨 / 미세먼지 / 자외선 / 복약 알림 / 학생 시간표를 한 화면에 표시한다.

## 현재 단계

- [x] 1단계: 프로젝트 뼈대 (디렉토리 구조, requirements.txt, FastAPI 기본 서버)
- [x] 2단계: 기상청 / 에어코리아 API 연동 (`.env` 기반 키 관리, 키 발급 전 mock 데이터로 동작)
- [x] 3단계: YAML 규칙 엔진 (조건 → 알림 메시지)
- [x] 4단계: 대시보드 UI (날씨/미세먼지/자외선/알림 카드, 5분마다 자동 갱신, 세로 모니터 대응, 강수/미세먼지 반응형 배경 효과)
- [ ] 5단계: 복약 알림 위젯 (확인 전까지 고정 노출)
- [ ] 6단계: 학생 시간표 위젯 (SQLite)
- [x] 화재 감지: Pi 센서 모듈 → 백엔드 → 홈 디스플레이 전체화면 경보 + 관리사무소 대시보드(`/admin`)

## 설치 및 실행

```bash
git clone https://github.com/ngcarl1225-ops/entrance-smart-display.git
cd entrance-smart-display
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

브라우저에서 http://localhost:8000 접속. 헬스체크는 `/health`.

### 업데이트 받기 (git pull)

이미 clone해둔 상태에서 최신 변경사항만 받아오려면:

```bash
git pull origin main
pip install -r requirements.txt   # 의존성이 바뀌었을 수 있으니 함께 실행 권장
```

`.env`는 git으로 관리되지 않으므로(gitignore) pull해도 내 설정값은 그대로 유지된다.
다만 `.env.example`에 새 항목이 추가된 경우, `git diff HEAD~1 -- .env.example` 등으로 확인해서 `.env`에 수동으로 반영해야 한다.

API 키 발급 전에는 `.env`의 `USE_MOCK_DATA=true` 상태로 아래 엔드포인트가 mock 데이터를 반환한다.
공공데이터포털에서 키를 받으면 `KMA_SERVICE_KEY` / `AIRKOREA_SERVICE_KEY`를 채우고 `USE_MOCK_DATA=false`로 바꾸면 된다.

- `GET /api/weather` — 기상청 단기예보 (강수확률/강수형태/기온/습도)
- `GET /api/uv` — 기상청 생활기상지수 (자외선지수)
- `GET /api/air-quality` — 에어코리아 대기오염정보 (PM10/PM2.5/통합대기환경지수)
- `GET /api/notifications` — 위 세 API를 종합해 `app/rules/rules.yaml` 규칙으로 평가한 알림 메시지 목록

### 설치 위치 자동 감지

`NX`/`NY`(기상청 격자), `AIRKOREA_STATION_NAME`, `KMA_UV_AREA_NO`를 IP 기반으로 자동 추정해 `.env`에 반영:

```bash
python scripts/sync_location.py
```

IP 기반 위치는 시/구 단위 근사치이므로, 실제 설치 주소와 다르면 `.env`에서 직접 값을 교정할 것.
특히 `AIRKOREA_STATION_NAME`은 반환된 구 이름이 실제 에어코리아 측정소명과 정확히 일치하는지 확인 필요.

## 화재 감지

라즈베리파이의 불꽃 센서(C57) + DS18B20 온도 센서를 매초 백엔드로 보고하고,
백엔드가 상태를 판정해 **홈 디스플레이**(각 세대 현관)와 **관리사무소 대시보드**에 실시간(SSE)으로 뿌린다.

### 상태 판정 (전부 백엔드 담당, Pi는 raw 값만 전송)

| 조건 | 상태 | 화면 동작 |
|---|---|---|
| 불꽃 + `FIRE_TEMP_THRESHOLD_C`(기본 50℃) 이상 동시 | `alarm` | 홈: 빨간 전체화면 + 사이렌 + 대피 안내 + 카운트다운 |
| `FIRE_ESCALATION_SECONDS`(기본 20초) 내 세대에서 취소 없음 | `escalated` | 관리사무소로 자동 통보 표시 |
| 불꽃 또는 고온 하나만 | `warning` | 홈: 주황 화면 + "확인하세요 / 오경보예요" 버튼 |
| 정상 | `normal` | 평상시 날씨 화면 |
| 마지막 보고 후 `FIRE_OFFLINE_SECONDS`(기본 30초) 끊김 | `offline` | 관리사무소에서 센서 이상으로 표시 (진행 중 경보는 유지) |

"오경보예요" 취소 시 `FIRE_CANCEL_COOLDOWN_SECONDS`(기본 60초) 동안 같은 잔여 신호로 재경보되지 않는다.
연결이 끊긴 센서의 오래된 값으로는 새 경보를 울리지 않는다(오프라인 처리).
단, 한 번도 보고된 적 없는 세대(`last_report`가 아예 없음)는 오프라인이 아니라 `normal`로 표시된다 —
실제 센서가 아직 안 붙은 세대와, 붙어 있다가 끊긴 세대를 구분하기 위함.

### 단지 구조 (관리사무소 화면에 자동으로 채워지는 세대 목록)

`.env`의 아래 값으로 동 x 층 x 층당세대 조합을 자동 생성한다. 호수는 "층×100+라인" 규칙
(예: 3층 2호 → `302호`, unit id는 `101-302`처럼 `동-호수`).

```bash
FIRE_BUILDINGS=101,102,103   # 동 목록 (콤마 구분)
FIRE_FLOORS=12                # 층수
FIRE_UNITS_PER_FLOOR=2        # 층당 세대수
```

기본값은 101~103동 x 12층 x 2세대 = 72세대. 이 조합 밖의 세대를 개별로 더 넣거나 표시이름을 바꾸고 싶으면
`FIRE_UNITS="아이디|표시이름"` 콤마 목록으로 추가 등록(자동 생성 결과 위에 덮어씀). 실제 센서(`fire_detection.py`)가
이 목록에 없는 `FIRE_UNIT_ID`로 보고하면 그 자리에서 새 세대로 자동 등록된다.

### 엔드포인트

- `POST /api/fire/report` — Pi가 매초 `{unit_id, flame, temperature, label?}` 전송 (heartbeat 겸용). `X-Fire-Token` 헤더로 인증(`FIRE_TOKEN` 설정 시)
- `POST /api/fire/cancel` — 홈 디스플레이의 "오경보예요" (`{unit_id}`)
- `POST /api/fire/ack` — 관리사무소 조치 `{unit_id, action}` (`checking` / `called_119` / `resolved`). `X-Admin-Token` 헤더로 인증(`FIRE_ADMIN_TOKEN` 설정 시)
- `GET /api/fire/units` — 전체 세대 스냅샷 / `GET /api/fire/state?unit_id=` — 한 세대
- `GET /api/fire/events?limit=` — 이력 (stdlib sqlite3, `data/fire_events.db`)
- `GET /api/fire/stream` — SSE. `?unit_id=` 주면 해당 세대만 (홈 디스플레이용), 없으면 전체 (관리사무소용)
- `POST /api/fire/simulate` — 발표 데모용 가짜 트리거 `{unit_id, scenario}` (`warning`/`alarm`/`clear`). `DEBUG=true`일 때만 동작

### 화면

- 홈 디스플레이: 기존 `/` 페이지에 화재 오버레이 레이어가 얹혀 있음. 담당 세대는 `?unit=101-302`로 지정(브라우저에 저장됨), 기본값 `101-302`
- 관리사무소: `/admin` — 2단계 구조
  - 기본 화면: 동 카드 3개(101/102/103동)만 크게 표시. 카드마다 "그 동에서 가장 심각한 상태" 색(정상 초록 / 주의 주황 / 경보·통보 빨강 펄스)과 세대 수 요약
  - 동 카드를 누르면 그 동의 세대만 층별로 오름차순(1층부터) 나열된 상세 화면으로 드릴다운, "← 전체 동 보기"로 복귀
  - 상단 경보 배너(조치 버튼: 현장 확인 중 / 119 신고함 / 상황 종료) + 하단 이력 테이블 + 데모 트리거 패널은 동 선택과 무관하게 항상 표시

### 발표 데모 (센서 없이)

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# 브라우저 탭 2개: http://localhost:8000 (홈) / http://localhost:8000/admin (관리사무소)
# /admin 하단 "발표 데모용 트리거"에서 101-302 대상으로 [화재경보] 클릭
# -> 홈 화면 빨강 전환 + 카운트다운, 관리사무소 화면은 101동 카드가 빨갛게 (클릭하면 3층 2호가 경보로 표시)
# -> 20초 후 관리사무소에 "자동 통보됨"
# -> 홈에서 "오경보예요" 누르면 양쪽 다 해제
```

데모 트리거나 테스트로 세대 하나를 건드리면 그 세대만 `last_report`가 생겨서, 이후 실제 센서처럼 계속
보고하지 않으면 `FIRE_OFFLINE_SECONDS` 뒤에 "오프라인"으로 바뀐다(다른 미접촉 세대는 정상으로 남음).
발표 직전엔 서버를 한 번 재시작해서 상태를 깨끗하게 초기화하는 걸 추천.

키오스크(Pi) 브라우저에서 경보음/음성이 자동 재생되려면 Chromium을 `--autoplay-policy=no-user-gesture-required` 로 실행할 것.

### 라즈베리파이(센서 모듈) 설정

`FIRE_UNIT_ID`가 곧 "이 센서가 어느 세대인지"를 정한다 — 관리사무소 화면에서 그 id로 뜬다.
디스플레이 서버와 같은 Pi에서 돌린다면 `FIRE_BACKEND_URL`은 기본값(`http://localhost:8000`)으로 충분하다.

```bash
# .env 에 추가 (또는 셸 export)
FIRE_UNIT_ID=101-302
FIRE_UNIT_LABEL=101동 302호
# 디스플레이 서버가 다른 기기일 때만 필요
# FIRE_BACKEND_URL=http://<디스플레이-서버-IP>:8000
# export FIRE_TOKEN=<서버 FIRE_TOKEN 과 동일>

python scripts/fire_detection.py
```

DS18B20은 1-Wire(`dtoverlay=w1-gpio,gpiopin=17`)로 연결하면 커널이 `/sys/bus/w1/devices/28-*`에 자동 등록한다 —
연결 직후 `ls /sys/bus/w1/devices/ | grep ^28-`로 잡히는지 먼저 확인할 것 (안 잡히면 스크립트가 시작하자마자 에러로 종료됨).
불꽃 센서 DO는 기본 GPIO4(`FIRE_FLAME_GPIO`로 변경 가능). 백엔드 연결이 끊겨도 스크립트는 죽지 않고 재시도한다.

**디지털 입력 핀은 gpiozero가 아니라 `scripts/_gpio_compat.py`(libgpiod의 `gpioget` CLI 호출)로 읽는다.**
Pi 5(RP1)에서 pip의 `lgpio` 패키지가 이 칩을 여는 데 재현 가능하게 실패하는 경우가 있어서 우회한 것.
`gpioget`/`gpiodetect`가 없으면 `sudo apt install gpiod`로 설치. Pi 4 이하에서도 그대로 동작한다
(`gpiodetect`가 `pinctrl-rp1` 라벨을 못 찾으면 `gpiochip0`으로 폴백).

## 프로젝트 구조

```
entrance-display/
├── app/
│   ├── main.py                # FastAPI 진입점
│   ├── services/               # 외부 API 연동 (기상청, 에어코리아)
│   ├── rules/                  # 규칙 기반 알림 엔진 + rules.yaml
│   ├── fire/                   # 화재 감지 (state.py 상태판정, router.py API, store.py 이력)
│   ├── medication/              # 복약 알림
│   ├── schedule/                # 학생 시간표
│   ├── db/                      # SQLAlchemy 모델
│   └── static/                  # 프론트엔드 (index.html 홈, admin.html 관리사무소)
├── config/
│   └── settings.py              # 환경설정 (pydantic-settings)
├── scripts/
│   ├── sync_location.py         # IP 기반 설치 위치 자동 감지 → .env 반영
│   └── fire_detection.py        # 라즈베리파이 센서 → 백엔드 보고
├── requirements.txt
└── .env.example
```
