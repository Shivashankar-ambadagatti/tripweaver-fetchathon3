from uagents import Model


class WeatherRequest(Model):
    lat: float
    lon: float
    start: str          # YYYY-MM-DD
    days: int
    simulate_rain: bool


class WeatherResponse(Model):
    days_json: str      # list of daily weather dicts as a JSON string

class BudgetRequest(Model):
    people: int
    days: int
    budget: int         # 0 means "no budget given"


class BudgetResponse(Model):
    tier: str
    breakdown_json: str  # the chosen tier's cost breakdown as JSON

class ItineraryRequest(Model):
    facts_json: str     # destination, people, days, tier, budget breakdown, weather


class ItineraryResponse(Model):
    plan_text: str