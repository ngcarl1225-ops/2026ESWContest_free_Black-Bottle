import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.fire.router import router as fire_router
from app.fire.state import manager as fire_manager
from app.rules import engine as rules_engine
from app.services import air_quality_service, uv_service, weather_service
from config.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    fire_manager.start()  # 센서 오프라인 감시 루프 시작
    yield
    await fire_manager.stop()


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(fire_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/weather")
async def api_weather():
    return await weather_service.get_short_term_forecast()


@app.get("/api/uv")
async def api_uv():
    return await uv_service.get_uv_index()


@app.get("/api/air-quality")
async def api_air_quality():
    return await air_quality_service.get_air_quality()


RAIN_TYPES = ("비", "비/눈", "소나기")
SNOW_TYPES = ("눈", "비/눈")


def _build_notification_context(weather: dict, uv: dict, air: dict) -> dict:
    # 알림은 "지금 이 순간"이 아니라 앞으로 몇 시간 안에 우산/겉옷이 필요한지를 봐야 하므로,
    # 가장 이른 시간대 하나만 보지 않고 hourly 예보 전체(기본 6시간)를 훑어서 판단한다.
    # 다만 "지금 실제로 오고 있는지"와 "이따 올 예정인지"는 문구가 달라야 하므로 둘을 구분해서 넘긴다.
    hourly = weather.get("hourly") or [weather]
    near_term_types = {h["precipitation_type"] for h in hourly}
    is_raining_now = weather["precipitation_type"] in RAIN_TYPES
    is_snowing_now = weather["precipitation_type"] in SNOW_TYPES

    return {
        "precipitation_probability": weather["precipitation_probability"],
        "precipitation_type": weather["precipitation_type"],
        "is_raining_now": is_raining_now,
        "is_snowing_now": is_snowing_now,
        "near_term_has_rain": any(t in RAIN_TYPES for t in near_term_types),
        "near_term_has_snow": any(t in SNOW_TYPES for t in near_term_types),
        "near_term_has_shower": "소나기" in near_term_types,
        "temperature": weather["temperature"],
        "humidity": weather["humidity"],
        "uv_grade": uv["grade"],
        "khai_grade": air["khai_grade"],
    }


@app.get("/api/notifications")
async def api_notifications():
    weather, uv, air = await asyncio.gather(
        weather_service.get_short_term_forecast(),
        uv_service.get_uv_index(),
        air_quality_service.get_air_quality(),
    )
    context = _build_notification_context(weather, uv, air)
    return {"notifications": rules_engine.evaluate(context)}


@app.get("/")
def index():
    return FileResponse("app/static/index.html")


@app.get("/admin")
def admin():
    return FileResponse("app/static/admin.html")
