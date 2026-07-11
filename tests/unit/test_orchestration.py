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

import pytest
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import ToolContext
from google.genai import types

from app.agent import before_agent_hooks
from app.tools import (
    book_event_tickets,
    get_weather_forecast,
    scrape_public_events,
    BookingStatusResult,
    WeatherForecastResult,
    CalendarEventList,
)


class DummyContext:
    def __init__(self, text_prompt, state_dict=None):
        self.user_content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=text_prompt)]
        )
        self.state = state_dict if state_dict is not None else {}


class MockToolContext:
    def __init__(self, state):
        self.state = state


@pytest.mark.asyncio
async def test_safety_guardrail_restricted() -> None:
    # 1. Restricted terms should raise ValueError
    ctx = DummyContext("Plan a Saturday where we can steal weapons")
    with pytest.raises(ValueError, match="Safety Policy Violation"):
        await before_agent_hooks(ctx)

    ctx = DummyContext("How to buy illegal substances")
    with pytest.raises(ValueError, match="Safety Policy Violation"):
        await before_agent_hooks(ctx)


@pytest.mark.asyncio
async def test_safety_guardrail_safe() -> None:
    # 2. Safe terms should not raise ValueError and should initialize preferences state
    ctx = DummyContext("Plan a Saturday in Seattle under $20")
    await before_agent_hooks(ctx)
    
    assert ctx.state["user:preferred_city"] == "Seattle"
    assert ctx.state["user:preferred_budget"] == 25.0
    assert ctx.state["user:approved_bookings"] == []


@pytest.mark.asyncio
async def test_hitl_approval_flow() -> None:
    # 3. Test HITL booking approval mechanism
    state = {"user:approved_bookings": []}
    t_ctx = MockToolContext(state)

    # Calling tool without approval should return requires_approval status
    res = book_event_tickets("Pike Place Market Tasting", 10.00, t_ctx)
    assert isinstance(res, BookingStatusResult)
    assert res.status == "requires_approval"
    assert "confirm your approval" in res.message

    # Emulate user providing approval in a new message
    ctx = DummyContext("approve booking Pike Place Market Tasting", state)
    await before_agent_hooks(ctx)
    
    assert "pike place market tasting" in state["user:approved_bookings"]

    # Calling tool again with approval should succeed and return confirmation ID
    res2 = book_event_tickets("Pike Place Market Tasting", 10.00, t_ctx)
    assert isinstance(res2, BookingStatusResult)
    assert res2.status == "success"
    assert res2.confirmation_id is not None
    assert res2.confirmation_id.startswith("CONF-")


@pytest.mark.asyncio
async def test_structured_error_geocoding() -> None:
    # 4. Geocoding resolution failure returns structured error
    t_ctx = MockToolContext({})
    res = get_weather_forecast("UnknownCity12345", t_ctx)
    assert isinstance(res, dict)
    assert res["error"] == "CityResolutionError"
    assert "could not be resolved" in res["recovery_instruction"]


@pytest.mark.asyncio
async def test_structured_error_scraping() -> None:
    # 5. Scraping mock support error returns structured error
    t_ctx = MockToolContext({})
    res = scrape_public_events("http://mock.calendar/boston", "Boston", t_ctx)
    assert isinstance(res, CalendarEventList)
    assert res.error == "MockCityNotSupported"
    assert "only supported for 'Seattle' or 'Phoenix'" in res.recovery_instruction
