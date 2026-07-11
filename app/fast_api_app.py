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

import contextlib
import os
import re
from collections.abc import AsyncIterator

import google.auth
from a2a.server.tasks import InMemoryTaskStore
from dotenv import load_dotenv
from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.runners import Runner
from google.cloud import logging as google_cloud_logging

from app.app_utils import services
from app.app_utils.a2a import attach_a2a_routes
from app.app_utils.reasoning_engine_adapter import (
    attach_reasoning_engine_routes,
)
from app.app_utils.telemetry import (
    setup_agent_engine_telemetry,
    setup_telemetry,
)
from app.app_utils.typing import Feedback

load_dotenv()
setup_telemetry()
# Must run before get_fast_api_app to set the tracer provider resource.
setup_agent_engine_telemetry()
_, project_id = google.auth.default()
logging_client = google_cloud_logging.Client()
logger = logging_client.logger(__name__)
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Runner for the A2A path, sharing the same session/artifact services as the
    # adk_api and reasoning_engine paths (see services.py). Imported here so the
    # agent is built after env/telemetry setup.
    from app.agent import app as adk_app
    from app.agent import root_agent

    runner = Runner(
        app=adk_app,
        session_service=services.get_session_service(),
        artifact_service=services.get_artifact_service(),
        auto_create_session=True,
    )
    # Shared by the A2A path and the reasoning_engine adapter routes.
    app.state.runner = runner
    app.state.agent_app_name = adk_app.name
    await attach_a2a_routes(
        app,
        agent=root_agent,
        runner=runner,
        task_store=InMemoryTaskStore(),
        rpc_path=f"/a2a/{adk_app.name}",
    )
    yield


app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=services.ARTIFACT_SERVICE_URI,
    allow_origins=allow_origins,
    session_service_uri=services.SESSION_SERVICE_URI,
    otel_to_cloud=False,
    lifespan=lifespan,
)
app.title = "concierge-agent"
app.description = "API for interacting with the Agent concierge-agent"


# Proxy routes so the Vertex AI Console Playground (reasoning_engine SDK) can
# talk to this agent alongside the native adk_api routes.
attach_reasoning_engine_routes(app)


def redact_pii(text: str) -> str:
    """Sanitize text to redact common PII formats (emails, phone numbers, SSNs, credit cards)."""
    if not text:
        return text
    # 1. Redact Emails
    email_regex = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    text = re.sub(email_regex, '[REDACTED_EMAIL]', text)
    # 2. Redact Phone Numbers (international and local formats)
    phone_regex = r'\+?\b(?:\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'
    text = re.sub(phone_regex, '[REDACTED_PHONE]', text)
    # 3. Redact Social Security Numbers (SSN)
    ssn_regex = r'\b\d{3}-\d{2}-\d{4}\b'
    text = re.sub(ssn_regex, '[REDACTED_SSN]', text)
    # 4. Redact Credit Card Numbers (13 to 16 digits)
    cc_regex = r'\b(?:\d[ -]*?){13,16}\b'
    text = re.sub(cc_regex, '[REDACTED_CARD]', text)
    return text


@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect, sanitize, and log feedback with intent vs outcome tracking.

    Args:
        feedback: The feedback data to log

    Returns:
        Success status dict
    """
    intent_str = feedback.intent or ""
    outcome_str = feedback.outcome or ""

    # Reconstruct from session service if missing
    if (not intent_str or not outcome_str) and feedback.session_id:
        try:
            ss = services.get_session_service()
            session = ss.get_session_sync(session_id=feedback.session_id)
            if session and session.events:
                # Extract first user message as intent
                user_msgs = []
                for ev in session.events:
                    if ev.author == "user" and ev.content:
                        text_parts = []
                        content_dict = ev.content.model_dump()
                        for part in content_dict.get("parts", []) or []:
                            if "text" in part and part["text"]:
                                text_parts.append(part["text"])
                        if text_parts:
                            user_msgs.append("".join(text_parts))
                if user_msgs and not intent_str:
                    intent_str = user_msgs[0]

                # Extract last model response as outcome
                model_msgs = []
                for ev in session.events:
                    if ev.author in ("model", "concierge_agent") and ev.content:
                        text_parts = []
                        content_dict = ev.content.model_dump()
                        for part in content_dict.get("parts", []) or []:
                            if "text" in part and part["text"]:
                                text_parts.append(part["text"])
                        if text_parts:
                            model_msgs.append("".join(text_parts))
                if model_msgs and not outcome_str:
                    outcome_str = model_msgs[-1]
        except Exception:
            pass

    # Sanitize and redact PII from all textual fields before logging
    sanitized_text = redact_pii(feedback.text or "")
    sanitized_intent = redact_pii(intent_str)
    sanitized_outcome = redact_pii(outcome_str)

    log_payload = feedback.model_dump()
    log_payload["text"] = sanitized_text
    log_payload["intent"] = sanitized_intent
    log_payload["outcome"] = sanitized_outcome

    logger.log_struct(log_payload, severity="INFO")
    return {"status": "success"}


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
