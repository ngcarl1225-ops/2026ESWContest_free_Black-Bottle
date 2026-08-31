from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Entrance Assistant Display"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    # 공공데이터포털 서비스키 - 발급 전에는 비워두면 mock 데이터로 동작
    kma_service_key: str = ""       # 기상청 단기예보 / 생활기상지수
    airkorea_service_key: str = ""  # 에어코리아 대기오염정보
    use_mock_data: bool = True      # 키 발급 전 강제 mock. 키 발급 후 false로 전환

    # 기상청 단기예보 격자좌표 (기본값: 서울 종로구). 실제 주소는 기상청 격자 변환표에서 조회
    nx: int = 60
    ny: int = 127

    # 에어코리아 측정소명 (한글, 예: "종로구")
    airkorea_station_name: str = "종로구"

    # 기상청 생활기상지수(자외선) 구역코드. nx/ny와 다른 별도 코드 체계이며,
    # 공공데이터포털 문서의 "생활기상지수 구역코드" 엑셀에서 조회 필요 (기본값: 서울)
    kma_uv_area_no: str = "1100000000"

    # ---------- 화재 감지 ----------
    # Pi 센서 모듈 -> 백엔드 인증용 공유 토큰. 비워두면 인증 없이 허용(로컬 데모 기본값).
    fire_token: str = ""
    # 관리사무소 대시보드의 조치(확인중/119신고/상황종료) 인증 토큰. 비워두면 누구나 허용.
    fire_admin_token: str = ""
    # 불꽃+고온 동시 감지(alarm) 후 세대에서 취소가 없으면 관리사무소로 자동 통보되기까지의 초.
    fire_escalation_seconds: int = 20
    # 마지막 보고 이후 이 시간(초)이 지나면 센서 오프라인으로 표시.
    fire_offline_seconds: int = 30
    # DS18B20 온도가 이 값(℃) 이상이면서 불꽃도 감지되면 화재 경보(alarm)로 판정.
    fire_temp_threshold_c: float = 50.0
    # "오경보예요" 취소 후 같은 잔여 신호로 즉시 재경보되지 않도록 무시하는 쿨다운(초).
    fire_cancel_cooldown_seconds: int = 60
    # 경보->주의->정상처럼 완화되는 방향으로 상태가 내려가려면 그 값이 이 시간(초) 동안
    # 안정적으로 유지돼야 반영한다. 라이터 불꽃처럼 순간적으로 깜빡이는 신호에 화면/사이렌이
    # 계속 껐다 켜졌다 하는 걸 막기 위함(위험해지는 방향은 디바운스 없이 즉시 반영).
    fire_debounce_seconds: int = 3
    # 관리사무소 화면에 자동으로 채워 넣을 단지 구조: 동 목록 x 층수 x 층당 세대수.
    # 호수는 "층*100 + 라인" 규칙으로 생성 (예: 3층 2호 -> 302호). 기본값: 101~103동, 12층, 층당 2세대.
    fire_buildings: str = "101,102,103"
    fire_floors: int = 12
    fire_units_per_floor: int = 2
    # 위 자동 생성 외에 개별로 추가/덮어쓸 세대. "아이디|표시이름" 을 콤마로 구분.
    # 예: "101-9999|관리사무소 테스트". 보통은 비워둔다.
    fire_units: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
