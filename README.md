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

## 실행 방법

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

브라우저에서 http://localhost:8000 접속. 헬스체크는 `/health`.

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

## 프로젝트 구조

```
entrance-display/
├── app/
│   ├── main.py                # FastAPI 진입점
│   ├── services/               # 외부 API 연동 (기상청, 에어코리아)
│   ├── rules/                  # 규칙 기반 알림 엔진 + rules.yaml
│   ├── medication/              # 복약 알림
│   ├── schedule/                # 학생 시간표
│   ├── db/                      # SQLAlchemy 모델
│   └── static/                  # 프론트엔드 (HTML/CSS/JS)
├── config/
│   └── settings.py              # 환경설정 (pydantic-settings)
├── scripts/
│   └── sync_location.py         # IP 기반 설치 위치 자동 감지 → .env 반영
├── requirements.txt
└── .env.example
```
