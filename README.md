# TripWeaver: Multi-Agent Trip Planner

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

**Fetch-A-Thon 3.0** | Team ID: `fetchathon3.0-5460` | Team lead: Shivashankar Ambadagatti

## Problem
Planning even a short trip means checking the weather, working out a budget and
building a schedule, then redoing it all when the forecast changes.

## What it does
Tell TripWeaver your destination, days, group size and budget in plain language, for example:
"Plan a two-day Mysuru trip for three people under ₹6,000."

TripWeaver coordinates specialist agents to:
1. Fetch the **live weather forecast** and flag rainy days.
2. Pick the **budget tier that fits** and give an itemized estimate.
3. Build a **day-by-day itinerary** that moves to indoor plans on rainy days.
4. Ask for your **approval**, and **re-plan on 'recheck'** with a refreshed forecast.

The whole workflow runs inside an ASI:One chat. No custom frontend is needed.

## Agents

| Agent | Role | Address |
|---|---|---|
| TripWeaver (Coordinator) | Chat Protocol entry point, understands the request, combines results | `agent1qgccqz0apedq5rnhkem5van6naxqzzee3me7llr2wf547lalcrvg7rm60gl` |
| TripWeaver-Weather | Live forecast (Open-Meteo), rain flags | `agent1qgrytjh0vgk6zyr373wwdgh4et40wvduhprawutkyvd8u0rwn239yu2rrrn` |
| TripWeaver-Budget | Picks the tier that fits and itemizes costs | `agent1qt43ewdcymwytzd2e0yr9gklnfkdp563d7lcfz39u02j8cr3d5zwv2yx4cp` |
| TripWeaver-Itinerary | Builds the weather-aware itinerary (ASI:One LLM) | `agent1q0v65fz0sx4xreu8lg0kstxkud2h7wk7mtdurw2vq7380shkmzqh2kl5kzm` |

Agentverse profile URLs:
- Coordinator:https://agentverse.ai/agents/details/agent1qgccqz0apedq5rnhkem5van6naxqzzee3me7llr2wf547lalcrvg7rm60gl/profile
- Weather: https://agentverse.ai/agents/details/agent1qgrytjh0vgk6zyr373wwdgh4et40wvduhprawutkyvd8u0rwn239yu2rrrn/profile
- Budget: https://agentverse.ai/agents/details/agent1qt43ewdcymwytzd2e0yr9gklnfkdp563d7lcfz39u02j8cr3d5zwv2yx4cp/profile
- Itinerary: https://agentverse.ai/agents/details/agent1q0v65fz0sx4xreu8lg0kstxkud2h7wk7mtdurw2vq7380shkmzqh2kl5kzm/profile

## Fetch.ai technology used
- **uAgents** framework, with all four agents registered on **Agentverse** (mailbox)
- **Agent Chat Protocol (ACP)** on the coordinator, so it is discoverable and usable from **ASI:One**
- **ASI:One LLM** for understanding the request and writing the itinerary
- Agent-to-agent messaging between the coordinator and the three specialists

## Reliability
If a specialist agent is unavailable, the coordinator falls back to built-in logic.
If an external call fails, the user gets a clear message instead of a crash.

## Important notes
- Costs are **rough estimates, not live prices**. Verify before booking.
- Weather data comes live from Open-Meteo. The demo phrase "Simulate rain" marks day 1 as rainy
  and is labelled "simulated" in the output.

## How to run it
1. Install Python 3.12 and create a virtual environment:
   ```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Get an ASI:One API key (asi1.ai/dashboard/api-keys). Never commit it.
3. In each agent file, replace the seed placeholder with your own secret phrase.
4. Start the specialists, each in its own terminal (the Itinerary agent needs the key):
   ```
   python weather_agent.py
   python budget_agent.py
   $env:ASI_API_KEY="your-key"
   python itinerary_agent.py
   ```
5. Copy each specialist's printed address into `WEATHER_ADDR`, `BUDGET_ADDR` and
   `ITINERARY_ADDR` in `agent.py`.
6. Start the coordinator:
   ```
   $env:ASI_API_KEY="your-key"
   python agent.py
   ```
7. For each agent, open its inspector link, then click Connect, then Mailbox.
8. In ASI:One, message the TripWeaver agent: "Plan a two-day Mysuru trip for three people under ₹6,000."
   Then reply `approve`, or `recheck simulate rain`.

## Demo
- ASI:One shared chat: PASTE_LINK
- Demo video: PASTE_LINK