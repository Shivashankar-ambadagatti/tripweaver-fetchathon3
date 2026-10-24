import asyncio
import json
import math
import os
import re
from datetime import datetime, date, timedelta, timezone
from uuid import uuid4
from models import (WeatherRequest, WeatherResponse, BudgetRequest, BudgetResponse,
                    ItineraryRequest, ItineraryResponse)
import requests
from openai import OpenAI
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    StartSessionContent,
    TextContent,
    chat_protocol_spec,
)

agent = Agent(
    name="TripWeaver",
    seed="REPLACE_WITH_YOUR_OWN_SECRET_PHRASE_MAIN",  # keep YOUR seed
    port=8000,
    mailbox=True,
)

chat_proto = Protocol(spec=chat_protocol_spec)
WEATHER_ADDR = "agent1qgrytjh0vgk6zyr373wwdgh4et40wvduhprawutkyvd8u0rwn239yu2rrrn"
CURRENT = {}
LAST={}
LAST_ANY = {} 

def remote_weather(lat, lon, start, days, simulate_rain):
    ctx, loop = CURRENT["ctx"], CURRENT["loop"]
    fut = asyncio.run_coroutine_threadsafe(
        ctx.send_and_receive(
            WEATHER_ADDR,
            WeatherRequest(lat=lat, lon=lon, start=start.isoformat(),
                           days=days, simulate_rain=simulate_rain),
            response_type=WeatherResponse,
            timeout=10,
        ),
        loop,
    )
    reply, _status = fut.result(timeout=5)
    if reply is None:
        raise RuntimeError("no reply from weather agent")
    data = json.loads(reply.days_json)
    if not data:
        raise RuntimeError("weather agent returned no data")
    return data


BUDGET_ADDR = "agent1qt43ewdcymwytzd2e0yr9gklnfkdp563d7lcfz39u02j8cr3d5zwv2yx4cp"
def remote_budget(people, days, budget):
    ctx, loop = CURRENT["ctx"], CURRENT["loop"]
    fut = asyncio.run_coroutine_threadsafe(
        ctx.send_and_receive(
            BUDGET_ADDR,
            BudgetRequest(people=people, days=days, budget=int(budget or 0)),
            response_type=BudgetResponse,
            timeout=10,
        ),
        loop,
    )
    reply, _status = fut.result(timeout=15)
    if reply is None:
        raise RuntimeError("no reply from budget agent")
    return reply.tier, json.loads(reply.breakdown_json)

ITINERARY_ADDR = "agent1q0v65fz0sx4xreu8lg0kstxkud2h7wk7mtdurw2vq7380shkmzqh2kl5kzm"


def remote_itinerary(facts: dict) -> str:
    ctx, loop = CURRENT["ctx"], CURRENT["loop"]
    fut = asyncio.run_coroutine_threadsafe(
        ctx.send_and_receive(
            ITINERARY_ADDR,
            ItineraryRequest(facts_json=json.dumps(facts, ensure_ascii=False)),
            response_type=ItineraryResponse,
            timeout=60,
        ),
        loop,
    )
    reply, _status = fut.result(timeout=65)
    if reply is None or not reply.plan_text:
        raise RuntimeError("itinerary agent returned nothing")
    return reply.plan_text

ASI_MODEL = os.getenv("ASI_MODEL", "asi1")
client = OpenAI(base_url="https://api.asi1.ai/v1", api_key=os.getenv("ASI_API_KEY"))

# ---------------- helpers ----------------

def now_utc():
    return datetime.now(timezone.utc)


def create_text_chat(text: str) -> ChatMessage:
    return ChatMessage(
        timestamp=now_utc(),
        msg_id=uuid4(),
        content=[TextContent(type="text", text=text)],
    )


def llm(system: str, user: str, max_tokens: int = 1500) -> str:
    r = client.chat.completions.create(
        model=ASI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
    )
    return r.choices[0].message.content


# ---------------- tool 1: understand the request ----------------

EXTRACT_PROMPT = """Extract trip details from the user's message. Today is {today}.
Reply with ONLY a JSON object, no other text, with these keys:
destination (string or null), origin (string or null), days (integer, default 2),
people (integer, default 1), budget_inr (integer or null),
start_date (YYYY-MM-DD or null if not stated)."""


def extract_trip(text: str) -> dict:
    raw = llm(EXTRACT_PROMPT.format(today=date.today().isoformat()), text, 300)
    raw = re.sub(r"```json|```", "", raw).strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    return json.loads(match.group(0))


# ---------------- tool 2: weather (real API call) ----------------

def geocode(place: str):
    r = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": place, "count": 1},
        timeout=10,
    )
    r.raise_for_status()
    results = r.json().get("results")
    if not results:
        return None
    top = results[0]
    return top["latitude"], top["longitude"], top.get("name", place)


def get_weather(lat: float, lon: float, start: date, days: int, simulate_rain: bool):
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
            "date": day,
            "available": True,
            "tmax": d["temperature_2m_max"][idx],
            "tmin": d["temperature_2m_min"][idx],
            "rain_prob": prob,
            "rain_mm": mm,
            "rainy": rainy,
            "simulated": simulated,
        })
    return out


# ---------------- tool 3: budget (plain Python, no LLM) ----------------
# ROUGH ESTIMATES in INR, NOT live prices. Adjust to your own research.



TIERS = {
    "standard": {"room_night": 2500, "food_pp_day": 600, "local_group_day": 700, "activities_pp_day": 300, "intercity_pp": 1200},
    "budget":   {"room_night": 1200, "food_pp_day": 350, "local_group_day": 400, "activities_pp_day": 150, "intercity_pp": 600},
    "economy":  {"room_night": 800,  "food_pp_day": 250, "local_group_day": 300, "activities_pp_day": 100, "intercity_pp": 500},
}


def estimate_budget(people: int, days: int, budget):
    nights = max(days - 1, 0)
    rooms = math.ceil(people / 2)
    result = {}
    for name, t in TIERS.items():
        stay = nights * rooms * t["room_night"]
        food = people * days * t["food_pp_day"]
        local = days * t["local_group_day"]
        acts = people * days * t["activities_pp_day"]
        inter = people * t["intercity_pp"]
        result[name] = {
            "Stay": stay, "Food": food, "Local transport": local,
            "Activities": acts, "Intercity travel (assumed)": inter,
            "Total": stay + food + local + acts + inter,
        }
    if budget:
        chosen = "economy"  # fallback if nothing fits
        for name in ("standard", "budget", "economy"):
            if result[name]["Total"] <= budget:
                chosen = name
                break
    else:
        chosen = "budget"
    return chosen, result[chosen], result


def fmt_inr(n: int) -> str:
    return f"₹{n:,}"


# ---------------- tool 4: itinerary (LLM, grounded on tool outputs) ----------------

ITINERARY_PROMPT = """You are TripWeaver's itinerary agent. Build a practical trip itinerary using
ONLY the facts provided (destination, people, days, weather, budget breakdown).
Rules:
- Give each day Morning / Afternoon / Evening.
- Keep activities inside the stated budget tier; do not invent prices or opening times.
- For every day marked RAINY, put indoor-friendly activities in the main plan and add a
  short 'Rain re-plan' line explaining what changed from a normal day.
- For dry days, you may include outdoor activities.
- Only suggest places you are confident exist in the destination; otherwise keep it general.
- End with one line: costs are estimates, verify prices and timings before booking.
Keep it concise and readable."""


def build_itinerary(trip: dict, place: str, weather: list, tier: str, breakdown: dict):
    facts = {
        "destination": place,
        "people": trip["people"],
        "days": trip["days"],
        "budget_tier": tier,
        "budget_breakdown_inr": breakdown,
        "weather": weather,
    }
    try:
        text = remote_itinerary(facts)
        print("ITINERARY: used remote Itinerary agent")
        return text
    except Exception as e:
        print(f"ITINERARY: remote failed, using fallback. Reason: {repr(e)}")
        return llm(ITINERARY_PROMPT, json.dumps(facts, ensure_ascii=False), 1400)


# ---------------- coordinator ----------------

def plan_trip(user_text: str) -> str:
    try:
        trip = extract_trip(user_text)
    except Exception:
        return ("I couldn't understand that. Try: 'Plan a two-day Mysuru trip for "
                "three people under ₹6,000.'")

    if not trip.get("destination"):
        return ("Where would you like to go? Tell me the destination, number of days, "
                "number of people and your budget.")

    trip["days"] = max(1, min(int(trip.get("days") or 2), 7))
    trip["people"] = max(1, int(trip.get("people") or 1))
    start = date.today() + timedelta(days=1)
    if trip.get("start_date"):
        try:
            start = date.fromisoformat(trip["start_date"])
        except ValueError:
            pass
    simulate_rain = "simulate rain" in user_text.lower()

    # weather
    weather, place = [], trip["destination"]
    weather_note = ""
    try:
        geo = geocode(trip["destination"])
        if geo is None:
            weather_note = "Couldn't find that place for the weather lookup, so the plan assumes no weather data."
        else:
            lat, lon, place = geo
            try:
                weather = remote_weather(lat, lon, start, trip["days"], simulate_rain)
            except Exception:
                weather = get_weather(lat, lon, start, trip["days"], simulate_rain)
    except Exception:
        weather_note = "Weather service was unavailable, so this plan has no forecast."

    # budget
    try:
        tier, breakdown = remote_budget(trip["people"], trip["days"], trip.get("budget_inr"))
    except Exception:
        tier, breakdown, _ = estimate_budget(trip["people"], trip["days"], trip.get("budget_inr"))
    total = breakdown["Total"]
    budget = trip.get("budget_inr")

    # report pieces built by code (real tool output)
    lines = [f"**TripWeaver plan: {place}** — {trip['days']} day(s), {trip['people']} people"]
    lines.append("\n**Weather (live forecast)**")
    if weather:
        for w in weather:
            if not w.get("available"):
                lines.append(f"- {w['date']}: forecast not available yet")
                continue
            tag = " ☔ RAINY" if w["rainy"] else ""
            sim = " (simulated for demo)" if w["simulated"] else ""
            lines.append(
                f"- {w['date']}: {w['tmin']:.0f}–{w['tmax']:.0f}°C, "
                f"rain chance {w['rain_prob']}%{tag}{sim}"
            )
    else:
        lines.append(f"- {weather_note}")

    lines.append(f"\n**Budget estimate ({tier} tier, rough estimates, not live prices)**")
    for k, v in breakdown.items():
        lines.append(f"- {k}: {fmt_inr(v)}")
    if budget:
        if total <= budget:
            lines.append(f"✅ Within your {fmt_inr(budget)} budget (about {fmt_inr(budget - total)} spare).")
        else:
            lines.append(
                f"⚠️ Over your {fmt_inr(budget)} budget by about {fmt_inr(total - budget)}. "
                "Try fewer days, fewer people, a closer destination, or cheaper stays."
            )

    # itinerary
    try:
        plan = build_itinerary(trip, place, weather, tier, breakdown)
    except Exception:
        plan = "I couldn't generate the day-by-day itinerary right now. Please try again."
    lines.append("\n**Itinerary**\n" + plan)

    if any(w.get("rainy") for w in weather):
        lines.append("\n☔ Rain is expected on at least one day, so I adjusted the plan above.")
    return "\n".join(lines)


# ---------------- chat protocol handlers ----------------

@chat_proto.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(
        sender,
        ChatAcknowledgement(timestamp=now_utc(), acknowledged_msg_id=msg.msg_id),
    )
    CURRENT["ctx"] = ctx
    CURRENT["loop"] = asyncio.get_running_loop()
    for item in msg.content:
        if isinstance(item, StartSessionContent):
            ctx.logger.info(f"Session started with {sender}")
        
        elif isinstance(item, TextContent):
            text = re.sub(r"@\S+", "", item.text).strip()   # remove @mentions
            low = text.lower()
            ctx.logger.info(f"User said: {text} (sender={sender[:20]}...)")
            try:
                saved = LAST.get(sender) or LAST_ANY.get("last")
                if low in ("approve", "yes", "confirm"):
                    if saved:
                        saved["approved"] = True
                        answer = ("✅ Plan approved and saved. Before your trip, reply 'recheck' "
                                  "and I'll check the live forecast again and re-plan if the weather changed.")
                    else:
                        answer = "I don't have a plan to approve yet. Send a trip request first."
                elif low.startswith("recheck"):
                    if saved:
                        request = saved["request"]
                        if "simulate rain" in low:
                            request += " Simulate rain."
                        plan = await asyncio.to_thread(plan_trip, request)
                        answer = "🔄 I rechecked the live forecast. Here is the updated plan:\n\n" + plan
                    else:
                        answer = "I don't have a plan to recheck yet. Send a trip request first."
                else:
                    plan = await asyncio.to_thread(plan_trip, text)
                    if plan.startswith("**TripWeaver plan"):
                        LAST[sender] = {"request": text, "approved": False}
                        LAST_ANY["last"] = LAST[sender]
                        plan += ("\n\n👉 Reply 'approve' to confirm this plan, or "
                                 "'recheck simulate rain' to re-plan.")
                    answer = plan
            except Exception as e:
                ctx.logger.error(f"Planning failed: {e}")
                answer = "Sorry, something went wrong while planning. Please try again."
            await ctx.send(sender, create_text_chat(answer))
        elif isinstance(item, EndSessionContent):
            ctx.logger.info(f"Session ended with {sender}")


@chat_proto.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.info(f"Ack from {sender} for {msg.acknowledged_msg_id}")


agent.include(chat_proto, publish_manifest=True)

if __name__ == "__main__":
    agent.run()