import datetime
import re
import json
import logging
from typing import Optional, List, Dict, Any, AsyncGenerator

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.workflow import Workflow, Edge, START
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.adk.tools import AgentTool
from google.genai import types
from pydantic import BaseModel, Field

from app.config import config
from database.db_helper import log_audit, log_notification, get_active_trip, get_hotel, get_flight, save_hotel, save_flight, save_itinerary, get_itinerary

# Import all sub-agents
from agents.planner_agent import planner_agent
from agents.flight_agent import flight_agent
from agents.hotel_agent import hotel_agent
from agents.weather_agent import weather_agent
from agents.budget_agent import budget_agent
from agents.transport_agent import transport_agent
from agents.notification_agent import notification_agent
from agents.emergency_agent import emergency_agent
from agents.memory_agent import memory_agent

# -----------------------------------------------------------------------------
# 1. Orchestrator Schema
# -----------------------------------------------------------------------------

class OrchestratorOutput(BaseModel):
    intent: str = Field(description="The traveler's intent: 'plan_trip', 'flight_update', 'weather_update', 'budget_update', 'emergency', or 'general'.")
    response: str = Field(description="The text response explaining what has been analyzed or what requires approval.")
    requires_approval: bool = Field(description="True if an action (like rescheduling hotel check-in, changing reservations, or sending emails) requires human-in-the-loop approval.")
    action_type: Optional[str] = Field(None, description="The type of action to approve (e.g., 'reschedule_hotel', 'change_activities', 'book_flight').")
    action_data: Optional[str] = Field(None, description="The JSON string or description representing parameters for the action.")

# -----------------------------------------------------------------------------
# 2. Security Setup
# -----------------------------------------------------------------------------

# PII regex patterns
_PII_PATTERNS = [
    (re.compile(r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b'), "[CREDIT_CARD_REDACTED]"),
    (re.compile(r'\b(?=[A-Z0-9]*\d)[A-Z0-9]{9}\b', re.IGNORECASE), "[PASSPORT_REDACTED]"),
    (re.compile(r'\b\d{3}-\d{3}-\d{4}\b'), "[PHONE_REDACTED]"),
    (re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'), "[EMAIL_REDACTED]"),
]

# Injection detection keywords
_INJECTION_KEYWORDS = [
    "ignore previous instructions",
    "disregard system prompt",
    "you are now an administrator",
    "override system rules",
    "jailbreak",
    "developer mode bypass"
]

def _scrub_pii(text: str) -> tuple[str, list[str]]:
    findings = []
    for pattern, replacement in _PII_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            findings.append(f"PII Redacted: {replacement.strip('[]')}")
            text = pattern.sub(replacement, text)
    return text, findings

def _detect_injection(text: str) -> list[str]:
    lower = text.lower()
    return [kw for kw in _INJECTION_KEYWORDS if kw in lower]

# -----------------------------------------------------------------------------
# 3. Model Configuration
# -----------------------------------------------------------------------------

gemini_model = Gemini(
    model=config.model,
    retry_options=types.HttpRetryOptions(attempts=3),
)

# -----------------------------------------------------------------------------
# 4. Main Orchestrator Agent (Wired with Sub-Agents as Tools)
# -----------------------------------------------------------------------------

orchestrator = LlmAgent(
    name="orchestrator",
    description="TripPilot-AI core orchestrator that parses travel intents and delegates to specialists.",
    model=gemini_model,
    instruction=(
        "You are TripPilot-AI, a proactive, state-of-the-art Travel Concierge coordinator. "
        "Your task is to analyze traveler requests or event triggers and delegate to specialized sub-agents:\n"
        "- For planning a new itinerary: Use `planner_agent` to create it, and `memory_agent` to load settings first.\n"
        "- When a flight delay is reported: Use `flight_agent` to fetch flight status and update delay. "
        "Use `hotel_agent` to fetch hotel status. If the late arrival requires check-in rescheduling, "
        "explain this in the response and set `requires_approval` to True, `action_type` to 'reschedule_hotel', "
        "and `action_data` to a JSON with keys 'new_check_in_time' and 'hotel_name'.\n"
        "- When a rain forecast or weather storm warning is reported: Use `weather_agent` to find indoor activities, "
        "then use `planner_agent` to swap outdoor sightseeing items. If changes are proposed, explain in response, "
        "set `requires_approval` to True, `action_type` to 'change_activities', and `action_data` to details of the replacement.\n"
        "- When a budget overrun or expense check is needed: Use `budget_agent` to query statuses, warning if limits are hit. "
        "If budget is exceeded, set `requires_approval` to False and suggest public transit or casual dining options from `budget_agent` tools.\n"
        "- For local transfer routes: Use `transport_agent`.\n"
        "- For emergencies or lost passport checklists: Use `emergency_agent`.\n"
        "\n"
        "Fill out the structured OrchestratorOutput schema carefully."
    ),
    tools=[
        AgentTool(planner_agent),
        AgentTool(flight_agent),
        AgentTool(hotel_agent),
        AgentTool(weather_agent),
        AgentTool(budget_agent),
        AgentTool(transport_agent),
        AgentTool(notification_agent),
        AgentTool(emergency_agent),
        AgentTool(memory_agent)
    ],
    output_schema=OrchestratorOutput,
)

# -----------------------------------------------------------------------------
# 5. Workflow Node Functions
# -----------------------------------------------------------------------------

def security_checkpoint(ctx: Context, node_input: types.Content) -> Event:
    """Security Checkpoint Node: Scrubs PII, checks for prompt injection, and logs audits."""
    user_prompt = ""
    if node_input and node_input.parts:
        user_prompt = "".join([p.text for p in node_input.parts if p.text])

    # 1. PII Redaction
    clean_prompt, pii_findings = _scrub_pii(user_prompt)
    if pii_findings:
        log_audit("WARNING", "PII_REDACTED", {"original": user_prompt, "findings": pii_findings})

    # 2. Injection Check
    injections = _detect_injection(clean_prompt)
    if injections:
        log_audit("CRITICAL", "PROMPT_INJECTION_BLOCKED", {"keywords": injections})
        return Event(
            output=OrchestratorOutput(
                intent="general",
                response="⚠️ Blocked: Prompt injection attempt detected. Operation aborted.",
                requires_approval=False
            ),
            route="SECURITY_EVENT"
        )

    log_audit("INFO", "SECURITY_PASSED", {"pii_redacted": bool(pii_findings)})
    ctx.state["clean_prompt"] = clean_prompt
    return Event(output=clean_prompt)

def router(ctx: Context, node_input: OrchestratorOutput) -> Event:
    """Routes based on whether orchestrator requires HITL approval."""
    ctx.state["orchestrator_output"] = node_input.model_dump()
    
    if node_input.requires_approval:
        return Event(output=node_input.model_dump(), route="needs_approval")
    return Event(output=node_input.model_dump())

async def hitl_confirmation(ctx: Context, node_input: dict) -> AsyncGenerator[Event, None]:
    """Human-in-the-loop confirmation node for booking modifications."""
    action_type = node_input.get("action_type")
    action_data_str = node_input.get("action_data") or "{}"
    
    # Try parsing action data
    try:
        action_data = json.loads(action_data_str)
    except Exception:
        action_data = {"raw": action_data_str}
        
    interrupt_id = "confirm_travel_change"
    
    # Check if we need to request input
    if not ctx.resume_inputs or interrupt_id not in ctx.resume_inputs:
        msg = f"⚠️ TripPilot-AI Action Approval Request:\n"
        if action_type == "reschedule_hotel":
            msg += f"reschedule hotel check-in to: {action_data.get('new_check_in_time')} due to flight delay."
        elif action_type == "change_activities":
            msg += f"swap outdoor attractions with: {action_data.get('indoor_alt', 'Mori Art Museum & teamLab Planets')} due to weather."
        else:
            msg += f"execute change details: {action_data_str}"
            
        yield RequestInput(
            interrupt_id=interrupt_id,
            message=f"{msg}\nType 'yes' or 'confirm' to approve, or 'no' to cancel."
        )
        return

    # Check user response defensively (can be string or dict)
    user_response_val = ctx.resume_inputs.get(interrupt_id, "")
    if isinstance(user_response_val, dict):
        user_response = str(user_response_val.get("result", "") or user_response_val.get("response", "")).lower().strip()
    else:
        user_response = str(user_response_val).lower().strip()
    trip = get_active_trip("user_1")
    trip_id = trip["id"] if trip else 1
    
    if user_response in ["yes", "confirm", "y"]:
        # Execute the action
        if action_type == "reschedule_hotel":
            new_check_in = action_data.get("new_check_in_time", "8:00 PM")
            hotel = get_hotel(trip_id)
            if hotel:
                h_dict = dict(hotel)
                h_dict["check_in_time"] = new_check_in
                save_hotel(trip_id, h_dict)
            log_notification(trip_id, f"Hotel rescheduled to {new_check_in}.", "EMAIL")
            log_audit("INFO", "HITL_APPROVED_RESCHEDULE_HOTEL", {"trip_id": trip_id, "new_check_in": new_check_in})
            yield Event(output={"response": f"✅ Hotel check-in time updated successfully. Notification sent to companions."})
            
        elif action_type == "change_activities":
            # Adjust itinerary activities
            itinerary = get_itinerary(trip_id)
            if itinerary:
                # Update specific day activities to indoor
                for day in itinerary.get("days", []):
                    # Replace park or walk with museum
                    for act in day.get("activities", []):
                        if "park" in act["title"].lower() or "garden" in act["title"].lower():
                            act["title"] = "Mori Art Museum & teamLab Planets"
                            act["description"] = "Interactive digital art installations and contemporary exhibits."
                            act["cost"] = 3800.0
                save_itinerary(trip_id, itinerary)
            log_notification(trip_id, "Itinerary updated to indoor activities due to rain forecast.", "EMAIL")
            log_audit("INFO", "HITL_APPROVED_WEATHER_SWAP", {"trip_id": trip_id})
            yield Event(output={"response": "✅ Itinerary adjusted successfully. Swapped outdoor activities for museums. Notifications sent."})
        else:
            yield Event(output={"response": f"✅ Action '{action_type}' executed successfully."})
    else:
        log_audit("INFO", "HITL_REJECTED", {"trip_id": trip_id, "action_type": action_type})
        yield Event(output={"response": f"❌ Action '{action_type}' was declined. Bookings remain unchanged."})

def final_output(ctx: Context, node_input: dict) -> AsyncGenerator[Event, None]:
    """Renders final result and yields Content event for the playground UI."""
    response_text = node_input.get("response", "")
    
    # Emit UI content event so it displays in the playground
    yield Event(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=response_text)]
        )
    )
    # Yield output for the workflow engine terminal value
    yield Event(output=response_text)

def security_blocked_output(ctx: Context, node_input: OrchestratorOutput) -> AsyncGenerator[Event, None]:
    """Terminal node for blocked security events — renders a clear denial message."""
    response_text = node_input.response
    yield Event(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=response_text)]
        )
    )
    yield Event(output=response_text)

# -----------------------------------------------------------------------------
# 6. Workflow Definition & App
# -----------------------------------------------------------------------------

root_agent = Workflow(
    name="trippilot_workflow",
    description="Proactive Multi-Agent Travel Concierge Workflow",
    edges=[
        # START -> security checkpoint
        ("START", security_checkpoint),
        # security gate: blocked or orchestrator
        (security_checkpoint, {"SECURITY_EVENT": security_blocked_output}),
        (security_checkpoint, orchestrator),
        # orchestrator -> router
        (orchestrator, router),
        # router -> final output or hitl
        (router, {"needs_approval": hitl_confirmation}),
        (router, final_output),
        # HITL -> final output
        (hitl_confirmation, final_output),
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
)
