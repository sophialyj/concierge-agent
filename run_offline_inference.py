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

import os
import json
import asyncio
from pathlib import Path
import dotenv

# Load environment variables (API keys, etc.) from .env
dotenv.load_dotenv()

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from app.agent import root_agent

async def run_case(case_id, prompt_content):
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="app")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="app")

    print(f"Running inference for case: {case_id}...")
    
    # Run the agent
    events = list(runner.run(new_message=prompt_content, user_id="test_user", session_id=session.id))
    
    normalized_events = []
    # Add initial user prompt event
    normalized_events.append({
        "author": "user",
        "content": prompt_content.model_dump(exclude_none=True)
    })
    
    final_text = ""
    for ev in events:
        author = ev.author
        # Treat model / concierge_agent author as "concierge_agent"
        if author in ("model", "root_agent"):
            author = "concierge_agent"
            
        content_dict = None
        if ev.content:
            content_dict = ev.content.model_dump(exclude_none=True)
            # Strip binary thought signatures to avoid JSON serialization failures
            for part in content_dict.get("parts", []):
                part.pop("thought_signature", None)
                # Keep final response text if present
                if "text" in part and part["text"]:
                    final_text = part["text"]
                    
        normalized_events.append({
            "author": author,
            "content": content_dict
        })
        
    responses = []
    if final_text:
        responses.append({
            "response": {
                "role": "model",
                "parts": [{"text": final_text}]
            }
        })
        
    return {
        "eval_case_id": case_id,
        "prompt": prompt_content.model_dump(exclude_none=True),
        "responses": responses,
        "agent_data": {
            "agents": {
                "concierge_agent": {
                    "agent_id": "concierge_agent",
                    "agent_type": "LlmAgent",
                    "instruction": root_agent.instruction
                }
            },
            "turns": [
                {
                    "turn_index": 0,
                    "turn_id": "turn_0",
                    "events": normalized_events
                }
            ]
        }
    }

async def main():
    dataset_path = Path("tests/eval/datasets/itinerary-dataset.json")
    if not dataset_path.exists():
        print(f"Dataset {dataset_path} does not exist.")
        return

    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    results = []
    for case in dataset.get("eval_cases", []):
        case_id = case.get("eval_case_id")
        prompt_dict = case.get("prompt")
        
        # Reconstruct types.Content
        parts = [types.Part.from_text(text=p.get("text")) for p in prompt_dict.get("parts", [])]
        prompt_content = types.Content(role=prompt_dict.get("role", "user"), parts=parts)
        
        try:
            res_case = await run_case(case_id, prompt_content)
            results.append(res_case)
        except Exception as e:
            print(f"Failed case {case_id}: {e}")

    output_dir = Path("artifacts/traces")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "traces.json"
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"eval_cases": results}, f, indent=2)
        
    print(f"Successfully generated offline traces in: {output_path}")

if __name__ == "__main__":
    asyncio.run(main())
