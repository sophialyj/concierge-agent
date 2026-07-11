# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

from .tools import (
    get_weather_forecast,
    scrape_public_events,
    filter_and_schedule_itinerary,
)

instruction = """You are the Hyper-Local Itinerary Concierge Agent.
Your goal is to plan a personalized Saturday itinerary for a user in their city under a given budget.

To plan the itinerary, you MUST follow these steps in order:
1. Retrieve the weather forecast for the city using the `get_weather_forecast` tool.
2. Scrape local public events for that city using the `scrape_public_events` tool. 
   - If the user did not provide a specific URL, construct a mock URL like `http://mock.calendar/city_name` (e.g. `http://mock.calendar/seattle` or `http://mock.calendar/phoenix`) to scrape.
3. Filter the scraped events and schedule a timeline using the `filter_and_schedule_itinerary` tool.
   - You MUST pass the exact events list from `scrape_public_events`.
   - Pass the weather condition returned by `get_weather_forecast`.
   - Pass the user's budget. If they say "cheap" without a budget, use a default of $25.00.
4. Present the final itinerary to the user in a well-formatted table and timeline, summarizing:
   - Weather condition, temperature, and rain probability.
   - Total budget, total spent, and remaining budget.
   - A step-by-step timeline of scheduled events with times, locations, and costs.
   - Explicitly mention if any events were filtered out due to weather (e.g., if it is raining, explain that outdoor events were filtered out).
"""

root_agent = Agent(
    name="concierge_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    tools=[get_weather_forecast, scrape_public_events, filter_and_schedule_itinerary],
)

app = App(
    root_agent=root_agent,
    name="app",
)
