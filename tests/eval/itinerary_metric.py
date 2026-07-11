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

def evaluate(instance):
    """Deterministic evaluation of itinerary logic (budget and weather routing)."""
    # 1. Parse budget from user prompt
    prompt = instance.get("prompt", "")
    if isinstance(prompt, dict):
        parts = prompt.get("parts", [])
        prompt_text = "".join([p.get("text", "") for p in parts])
    else:
        prompt_text = str(prompt)
        
    budget = 25.0
    budget_match = re.search(r'\$?([0-9]+)', prompt_text)
    if budget_match:
        budget = float(budget_match.group(1))
    elif "cheap" in prompt_text.lower():
        budget = 25.0

    # 2. Extract agent execution trace
    agent_data = instance.get("agent_data", {})
    turns = agent_data.get("turns", [])
    
    tool_resp_data = None
    weather_cond = None
    
    # Scan turns for tool responses
    for turn in turns:
        for event in turn.get("events", []) or []:
            for part in event.get("content", {}).get("parts", []) or []:
                func_resp = part.get("function_response")
                if func_resp:
                    if func_resp.get("name") == "filter_and_schedule_itinerary":
                        tool_resp_data = func_resp.get("response", {})
                    elif func_resp.get("name") == "get_weather_forecast":
                        weather_resp = func_resp.get("response", {})
                        weather_cond = weather_resp.get("condition")

    # Fallback to direct event scanning
    if not tool_resp_data:
        for event in agent_data.get("events", []) or []:
            for part in event.get("content", {}).get("parts", []) or []:
                func_resp = part.get("function_response")
                if func_resp:
                    if func_resp.get("name") == "filter_and_schedule_itinerary":
                        tool_resp_data = func_resp.get("response", {})
                    elif func_resp.get("name") == "get_weather_forecast":
                        weather_resp = func_resp.get("response", {})
                        weather_cond = weather_resp.get("condition")

    if not tool_resp_data:
        return {"score": 1, "explanation": "filter_and_schedule_itinerary tool response not found in execution trace."}

    # 3. Validate budget
    total_spent = tool_resp_data.get("total_spent", 0.0)
    if total_spent > budget:
        return {"score": 2, "explanation": f"Failed budget constraint. Spent {total_spent} which exceeds budget of {budget}."}

    # 4. Validate weather routing
    schedule = tool_resp_data.get("schedule", [])
    if weather_cond and weather_cond.lower() == "rain":
        for ev in schedule:
            if ev.get("is_outdoor", False):
                return {"score": 3, "explanation": f"Failed weather constraint. Scheduled outdoor event '{ev.get('name')}' on a rainy day."}

    # 5. Check if it's empty but shouldn't be
    if budget > 0 and not schedule:
        return {"score": 4, "explanation": "Itinerary schedule is empty, indicating failure to plan any events."}

    return {"score": 5, "explanation": f"Successfully planned itinerary within budget ({total_spent} <= {budget}) and weather constraints (condition was {weather_cond})."}
