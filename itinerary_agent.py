import asyncio
import os

from openai import OpenAI
from uagents import Agent, Context

from models import ItineraryRequest, ItineraryResponse

agent = Agent(
    name="TripWeaver-Itinerary",
    seed="REPLACE_WITH_YOUR_OWN_SECRET_PHRASE_ITINERARY",
    port=8003,
    mailbox=True,
)

ASI_MODEL = os.getenv("ASI_MODEL", "asi1")
client = OpenAI(base_url="https://api.asi1.ai/v1", api_key=os.getenv("ASI_API_KEY"))

ITINERARY_PROMPT = """You are TripWeaver's itinerary agent. Build a practical trip itinerary using
ONLY the facts provided (destination, people, days, weather, budget breakdown).
Rules:
- Give each day Morning / Afternoon / Evening, one or two lines each.
- The trip has (days - 1) nights of stay. Do not say any other number of nights.
- Keep activities inside the stated budget tier; do not invent prices or opening times.
- For every day marked RAINY, put indoor-friendly activities in the main plan and add one
  short 'Rain re-plan' line explaining what changed from a normal day.
- If a day is marked simulated, treat it as rainy.
- For dry days, you may include outdoor activities.
- Only suggest places you are confident exist in the destination; otherwise keep it general.
- Do NOT repeat the budget breakdown or weather summary; they are shown separately.
- End with exactly one line: costs are estimates, verify prices and timings before booking.
Keep the whole answer under 350 words."""


def make_plan(facts_json: str) -> str:
    r = client.chat.completions.create(
        model=ASI_MODEL,
        messages=[
            {"role": "system", "content": ITINERARY_PROMPT},
            {"role": "user", "content": facts_json},
        ],
        max_tokens=2000,
    )
    return r.choices[0].message.content


@agent.on_event("startup")
async def hello(ctx: Context):
    ctx.logger.info(f"Itinerary agent address: {agent.address}")


@agent.on_message(ItineraryRequest, replies={ItineraryResponse})
async def handle(ctx: Context, sender: str, msg: ItineraryRequest):
    ctx.logger.info(f"Itinerary request from {sender}")
    try:
        text = await asyncio.to_thread(make_plan, msg.facts_json)
    except Exception as e:
        ctx.logger.error(f"Itinerary failed: {e}")
        text = ""
    await ctx.send(sender, ItineraryResponse(plan_text=text))


if __name__ == "__main__":
    agent.run()