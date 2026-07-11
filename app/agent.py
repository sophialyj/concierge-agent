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

import re
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.apps.app import EventsCompactionConfig
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
from google.adk.models import Gemini
from google.adk.plugins import LoggingPlugin
from google.adk.tools import request_input, AgentTool, google_search
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from .tools import (
    get_weather_forecast,
    scrape_public_events,
    filter_and_schedule_itinerary,
    book_event_tickets,
)

async def before_agent_hooks(callback_context: CallbackContext) -> None:
    """Pre-execution hook enforcing runtime safety policy and session state preferences."""
    # 1. Safety Guardrail: check prompt for forbidden keywords
    prompt_text = ""
    if callback_context.user_content and callback_context.user_content.parts:
        for part in callback_context.user_content.parts:
            if hasattr(part, "text") and part.text:
                prompt_text += part.text
    prompt_text = prompt_text.lower()
    
    forbidden_terms = ["weapons", "illegal", "drugs", "hacks", "steal", "robbery", "violence"]
    if any(term in prompt_text for term in forbidden_terms):
        raise ValueError("Safety Policy Violation: The requested prompt contains restricted or unsafe keywords.")

    # 2. Preferences state initialization
    state = callback_context.state
    if "user:preferred_city" not in state:
        state["user:preferred_city"] = "Seattle"
    if "user:preferred_budget" not in state:
        state["user:preferred_budget"] = 25.0
    if "user:approved_bookings" not in state:
        state["user:approved_bookings"] = []

    # 3. Parse booking confirmation approvals from new user message
    match = re.search(r'approve\s+booking\s+(.+)', prompt_text)
    if match:
        event_name = match.group(1).strip()
        if event_name not in state["user:approved_bookings"]:
            state["user:approved_bookings"].append(event_name)


# =====================================================================
# SPECIALIST AGENTS & STRATEGIC MODEL ROUTING
# =====================================================================

# 1. Weather Specialist Agent (Flash)
weather_agent = Agent(
    name="weather_agent",
    model=Gemini(model="models/gemini-flash-latest"),
    instruction=(
        "You are the Weather Specialist Agent. Your only goal is to retrieve the weather forecast "
        "for the upcoming Saturday in the given city using the `get_weather_forecast` tool and return the forecast result. "
        "If the tool response contains an `error` field, return the error and `recovery_instruction` directly to the coordinator."
    ),
    tools=[get_weather_forecast],
)

# 2. Calendar Scraper Specialist Agent (Flash)
scraper_agent = Agent(
    name="scraper_agent",
    model=Gemini(model="models/gemini-flash-latest"),
    instruction=(
        "You are the Calendar Scraper Specialist Agent. Your only goal is to scrape public Saturday "
        "calendar events for the target city using the `scrape_public_events` tool and return the list of events. "
        "If the tool response contains an `error` field, return the error and `recovery_instruction` directly to the coordinator."
    ),
    tools=[scrape_public_events],
)

# 3. Itinerary Planner & Booking Specialist Agent (Pro - Strategic Reasoning Model)
planner_agent = Agent(
    name="planner_agent",
    model=Gemini(model="models/gemini-pro-latest"),
    instruction=(
        "You are the Itinerary Planner Specialist Agent. Your task is to take the raw scheduled itinerary "
        "and weather data, format them into the required premium visual layout, and handle event ticket bookings "
        "if requested by the user.\n\n"
        "If the user asks to book tickets, call the `book_event_tickets` tool.\n"
        "If `book_event_tickets` returns a status of 'requires_approval', you MUST immediately stop, output the exact "
        "response message from the tool asking the user for confirmation, and wait for their reply. Do not generate a mock confirmation ID yourself.\n\n"
        "Present the final itinerary to the user using this exact premium visual layout:\n\n"
        "### 🌤️ [City Name] Weather Card\n"
        "┌──────────────────────────────────────────┐\n"
        "│ Condition: [Condition Emoji] [Condition] │\n"
        "│ Temperature: [Min Temp]°C to [Max Temp]°C │\n"
        "│ Rain Probability: [Rain]%                 │\n"
        "└──────────────────────────────────────────┘\n"
        "*[Provide a brief comment on whether outdoor events are available based on the weather]*\n\n"
        "### 💰 Budget Status\n"
        "- **Spent**: $[Total Spent] / $[Total Budget] [ProgressBar using ASCII blocks e.g. ■■■■□□□□□□]\n"
        "- **Remaining**: $[Remaining Budget]\n\n"
        "### 📅 Saturday Timeline\n"
        "[Start Time] ──● **[Event Name]**\n"
        "             │ 📍 Location: [Location]\n"
        "             │ 💵 Cost: [Cost]\n"
        "             │ 🏷️ Type: [Indoor/Outdoor]\n"
        "             ↓\n"
        "[Next Start Time] ...\n\n"
        "### ℹ️ Filtered & Excluded Events\n"
        "*   *[Detail why any scraped events were excluded, e.g. due to budget cap or schedule overlap]*\n"
    ),
    tools=[book_event_tickets],
)

# 4. Web Search Specialist Agent (Flash with Google Search Grounding)
search_agent = Agent(
    name="search_agent",
    model=Gemini(model="models/gemini-flash-latest"),
    instruction=(
        "You are the Search Specialist Agent. Your goal is to use the `google_search` tool to find Saturday public events, "
        "festivals, or local activities in the given city. Extract and return a clean list of events with details like "
        "name, estimated cost in dollars, venue/location, start/end times, and whether it is indoor or outdoor."
    ),
    tools=[google_search],
)

async def save_memories_callback(callback_context: CallbackContext) -> None:
    """Asynchronously saves the session history to long-term memory in a non-blocking background task."""
    import asyncio
    async def save_bg():
        try:
            # Sleep briefly to ensure response is fully sent and UI is updated without blocking
            await asyncio.sleep(0.5)
            await callback_context.add_session_to_memory()
        except Exception:
            pass
    # Schedule the coroutine as a background task to prevent UI blocking
    asyncio.create_task(save_bg())


# =====================================================================
# ROOT COORDINATOR / ORCHESTRATOR AGENT (Flash)
# =====================================================================
root_agent = Agent(
    name="concierge_agent",
    model=Gemini(
        model="models/gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are the Hyper-Local Itinerary Concierge Orchestrator Agent.\n"
        "Your goal is to coordinate a personalized Saturday planning workflow under the user's budget.\n\n"
        "If the user does not specify a city or budget, you MUST default to their saved preferences:\n"
        "- Saved City: {user:preferred_city}\n"
        "- Saved Budget: ${user:preferred_budget}\n\n"
        "To plan the itinerary, you MUST delegate tasks to your specialized sub-agents and tools in this order:\n"
        "1. If the user asks to plan a Saturday in a new city but does not specify which one, you MUST call the `request_input` tool with a hint asking them which city they have in mind.\n"
        "2. Call `weather_agent` to fetch the Saturday weather forecast for the target city.\n"
        "   - CRITICAL: If the weather_agent returns a response containing an `error` and a `recovery_instruction`, you MUST stop planning, notify the user, and call the `request_input` tool to ask them for clarification/input as directed.\n"
        "3. Gather the Saturday public events list for the target city:\n"
        "   - If a specific website URL was provided: Call `scraper_agent` to scrape it.\n"
        "   - If NO URL was provided, but the city is Seattle or Phoenix: Call `scraper_agent` with a mock URL like `http://mock.calendar/seattle` or `http://mock.calendar/phoenix` to fetch the mock events.\n"
        "   - If NO URL was provided and the city is NOT Seattle or Phoenix (for example, Palm Springs): Call the `search_agent` to find Saturday activities, local attractions, and events using Google Search.\n"
        "   - If `scraper_agent` is called but fails (e.g. returns a MockCityNotSupported or connection error), fall back and call the `search_agent` to find local events via Google Search instead of halting.\n"
        "4. Call the `filter_and_schedule_itinerary` tool directly using the weather condition and the list of events (obtained from scraper_agent or search_agent) under the user's budget.\n"
        "5. Call `planner_agent` to format the scheduled itinerary, handle ticket bookings if requested, and output the final response.\n\n"
        "CRITICAL EXECUTION RULE: You MUST execute all steps in sequence. Do NOT stop after step 2 or step 3. "
        "Under no circumstances should you return the weather forecast or scraped events list directly as the final response to the user. "
        "You must always call `filter_and_schedule_itinerary` and pass the results to the `planner_agent` in step 5, returning its output as the final result."
    ),
    tools=[
        PreloadMemoryTool(),
        AgentTool(weather_agent),
        AgentTool(scraper_agent),
        AgentTool(search_agent),
        AgentTool(planner_agent),
        filter_and_schedule_itinerary,
        request_input,
    ],
    before_agent_callback=before_agent_hooks,
    after_agent_callback=save_memories_callback,
)

# Configure Context Compaction to summarize older messages and keep tokens low
compaction_config = EventsCompactionConfig(
    compaction_interval=15,
    overlap_size=2,
    summarizer=LlmEventSummarizer(llm=Gemini(model="models/gemini-flash-latest")),
)

app = App(
    root_agent=root_agent,
    name="app",
    plugins=[LoggingPlugin()],
    events_compaction_config=compaction_config,
)
