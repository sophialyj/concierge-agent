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
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.apps.app import EventsCompactionConfig
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
from google.adk.models import Gemini
from google.adk.plugins import LoggingPlugin
from google.adk.tools import request_input
from google.genai import types

from .tools import (
    get_weather_forecast,
    scrape_public_events,
    filter_and_schedule_itinerary,
)

instruction = """You are the Hyper-Local Itinerary Concierge Agent.
Your goal is to plan a personalized Saturday itinerary for a user in their city under a given budget.

If the user does not specify a city or budget, you MUST default to their saved preferences:
- Saved City: {user:preferred_city}
- Saved Budget: ${user:preferred_budget}

To plan the itinerary, you MUST follow these steps in order:
1. If the user asks to plan a Saturday in a new city but does not specify which one, you MUST call the `request_input` tool with a hint asking them which city they have in mind.
2. Retrieve the weather forecast for the target city using the `get_weather_forecast` tool.
3. Scrape local public events for that city using the `scrape_public_events` tool. 
   - If the user did not provide a specific URL, construct a mock URL like `http://mock.calendar/city_name` (e.g. `http://mock.calendar/seattle` or `http://mock.calendar/phoenix`) to scrape.
4. Filter the scraped events and schedule a timeline using the `filter_and_schedule_itinerary` tool.
   - Pass the exact events list from `scrape_public_events`.
   - Pass the weather condition returned by `get_weather_forecast`.
   - Pass the user's budget.
5. Present the final itinerary to the user in a well-formatted table and timeline, summarizing:
   - Weather condition, temperature, and rain probability.
   - Total budget, total spent, and remaining budget.
   - A step-by-step timeline of scheduled events with times, locations, and costs.
   - Explicitly mention if any events were filtered out due to weather (e.g., if it is raining, explain that outdoor events were filtered out).
"""

async def initialize_state(callback_context: CallbackContext) -> None:
    """Initializes user-persistent preferences in the session state."""
    state = callback_context.state
    if "user:preferred_city" not in state:
        state["user:preferred_city"] = "Seattle"
    if "user:preferred_budget" not in state:
        state["user:preferred_budget"] = 25.0

root_agent = Agent(
    name="concierge_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    tools=[get_weather_forecast, scrape_public_events, filter_and_schedule_itinerary, request_input],
    before_agent_callback=initialize_state,
)

# Configure Context Compaction to summarize older messages and keep tokens low
compaction_config = EventsCompactionConfig(
    compaction_interval=15,
    overlap_size=2,
    summarizer=LlmEventSummarizer(llm=Gemini(model="gemini-flash-latest")),
)

app = App(
    root_agent=root_agent,
    name="app",
    plugins=[LoggingPlugin()],
    events_compaction_config=compaction_config,
)
