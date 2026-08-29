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

### 엔드포인트

- `POST /api/fire/report` — Pi가 매초 `{unit_id, flame, temperature, label?}` 전송 (heartbeat 겸용). `X-Fire-Token` 헤더로 인증(`FIRE_TOKEN` 설정 시)
- `POST /api/fire/cancel` — 홈 디스플레이의 "오경보예요" (`{unit_id}`)
- `POST /api/fire/ack` — 관리사무소 조치 `{unit_id, action}` (`checking` / `called_119` / `resolved`). `X-Admin-Token` 헤더로 인증(`FIRE_ADMIN_TOKEN` 설정 시)
- `GET /api/fire/units` — 전체 세대 스냅샷 / `GET /api/fire/state?unit_id=` — 한 세대
- `GET /api/fire/events?limit=` — 이력 (stdlib sqlite3, `data/fire_events.db`)
- `GET /api/fire/stream` — SSE. `?unit_id=` 주면 해당 세대만 (홈 디스플레이용), 없으면 전체 (관리사무소용)
- `POST /api/fire/simulate` — 발표 데모용 가짜 트리거 `{unit_id, scenario}` (`warning`/`alarm`/`clear`). `DEBUG=true`일 때만 동작

### 화면

- 홈 디스플레이: 기존 `/` 페이지에 화재 오버레이 레이어가 얹혀 있음. 담당 세대는 `?unit=101-1203`으로 지정(브라우저에 저장됨), 기본값 `101-1203`
- 관리사무소: `/admin` — 세대 그리드(초록/주황/빨강/회색) + 상단 경보 패널(조치 버튼) + 이력 테이블 + 데모 트리거 패널

### 발표 데모 (센서 없이)

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# 브라우저 탭 2개: http://localhost:8000 (홈) / http://localhost:8000/admin (관리사무소)
# /admin 하단 "발표 데모용 트리거"에서 101-1203 대상으로 [화재경보] 클릭
# -> 홈 화면 빨강 전환 + 카운트다운, 20초 후 관리사무소에 "자동 통보됨"
# -> 홈에서 "오경보예요" 누르면 양쪽 다 해제
```

키오스크(Pi) 브라우저에서 경보음/음성이 자동 재생되려면 Chromium을 `--autoplay-policy=no-user-gesture-required` 로 실행할 것.

### 라즈베리파이(센서 모듈) 설정

```bash
# 디스플레이 서버와 다른 Pi라면 .env 또는 셸에 지정
export FIRE_BACKEND_URL=http://<디스플레이-서버-IP>:8000
export FIRE_UNIT_ID=101-1203
export FIRE_UNIT_LABEL="101동 1203호"
# export FIRE_TOKEN=<서버 FIRE_TOKEN 과 동일>
python scripts/fire_detection.py
```

DS18B20은 1-Wire(`dtoverlay=w1-gpio`), 불꽃 센서 DO는 기본 GPIO4(`FIRE_FLAME_GPIO`로 변경). 백엔드 연결이 끊겨도 스크립트는 죽지 않고 재시도한다.

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
