import json
import math

from uagents import Agent, Context

from models import BudgetRequest, BudgetResponse

agent = Agent(
    name="TripWeaver-Budget",
    seed="REPLACE_WITH_YOUR_OWN_SECRET_PHRASE_BUDGET",
    port=8002,
    mailbox=True,
)

# ROUGH ESTIMATES in INR, not live prices.
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
        chosen = "economy"
        for name in ("standard", "budget", "economy"):
            if result[name]["Total"] <= budget:
                chosen = name
                break
    else:
        chosen = "budget"
    return chosen, result[chosen]


@agent.on_event("startup")
async def hello(ctx: Context):
    ctx.logger.info(f"Budget agent address: {agent.address}")


@agent.on_message(BudgetRequest, replies={BudgetResponse})
async def handle(ctx: Context, sender: str, msg: BudgetRequest):
    ctx.logger.info(f"Budget request from {sender}")
    budget = msg.budget if msg.budget > 0 else None
    tier, breakdown = estimate_budget(msg.people, msg.days, budget)
    await ctx.send(sender, BudgetResponse(tier=tier, breakdown_json=json.dumps(breakdown)))


if __name__ == "__main__":
    agent.run()