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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
