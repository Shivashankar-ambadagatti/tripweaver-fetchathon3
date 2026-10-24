import json
from datetime import date, timedelta

import requests
from uagents import Agent, Context

from models import WeatherRequest, WeatherResponse

agent = Agent(
    name="TripWeaver-Weather",
    seed="REPLACE_WITH_YOUR_OWN_SECRET_PHRASE_WEATHER",
    port=8001,
    endpoint=["http://127.0.0.1:8001/submit"],
)


def get_weather(lat, lon, start: date, days: int, simulate_rain: bool):
    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "daily": "precipitation_probability_max,precipitation_sum,temperature_2m_max,temperature_2m_min",
            "timezone": "auto",
            "forecast_days": 16,
        },
        timeout=10,
    )
    r.raise_for_status()
    d = r.json()["daily"]
    out = []
    for i in range(days):
        day = (start + timedelta(days=i)).isoformat()
        if day not in d["time"]:
            out.append({"date": day, "available": False})
            continue
        idx = d["time"].index(day)
        prob = d["precipitation_probability_max"][idx] or 0
        mm = d["precipitation_sum"][idx] or 0
        rainy = prob >= 60 or mm >= 5
        simulated = False
        if simulate_rain and i == 0:
            rainy, prob, simulated = True, max(prob, 80), True
        out.append({
            "date": day, "available": True,
            "tmax": d["temperature_2m_max"][idx],
            "tmin": d["temperature_2m_min"][idx],
            "rain_prob": prob, "rain_mm": mm,
            "rainy": rainy, "simulated": simulated,
        })
    return out


@agent.on_event("startup")
async def hello(ctx: Context):
    ctx.logger.info(f"Weather agent address: {agent.address}")


@agent.on_message(WeatherRequest, replies={WeatherResponse})
async def handle(ctx: Context, sender: str, msg: WeatherRequest):
    ctx.logger.info(f"Weather request from {sender}")
    try:
        data = get_weather(msg.lat, msg.lon, date.fromisoformat(msg.start),
                           msg.days, msg.simulate_rain)
    except Exception as e:
        ctx.logger.error(f"Weather failed: {e}")
        data = []
    await ctx.send(sender, WeatherResponse(days_json=json.dumps(data)))


if __name__ == "__main__":
    agent.run()