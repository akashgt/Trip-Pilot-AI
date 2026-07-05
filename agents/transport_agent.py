from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.genai import types
import json

def find_routes(origin: str, destination: str, preferred_mode: str = "Metro") -> str:
    """Finds available transit routes, including time, cost, and route description.
    
    Args:
        origin: Start location name or coordinates.
        destination: Destination name or coordinates.
        preferred_mode: Preferred mode of transport (e.g. Metro, Taxi, Walking, Train).
    """
    # Return simulated routes
    routes = [
        {
            "mode": "Metro",
            "route": "Tokyo Metro Ginza Line directly",
            "duration_minutes": 15,
            "cost_usd": 2.10,
            "instructions": f"Take Ginza Line from {origin} to {destination}."
        },
        {
            "mode": "Taxi",
            "route": "Expressway / Local Streets",
            "duration_minutes": 12,
            "cost_usd": 28.00,
            "instructions": f"Hail cab or call Uber from {origin} to {destination}."
        },
        {
            "mode": "Walking",
            "route": "Pedestrian paths",
            "duration_minutes": 45,
            "cost_usd": 0.00,
            "instructions": "Walk straight along the main avenue."
        }
    ]
    
    # Sort preferred_mode first
    routes.sort(key=lambda r: 0 if r["mode"].lower() == preferred_mode.lower() else 1)
    
    return json.dumps(routes, indent=2)

def get_gemini_model():
    from app.config import config
    return Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    )

transport_agent = LlmAgent(
    name="transport_agent",
    description="Finds transit options, calculates travel times, and estimates costs.",
    model=get_gemini_model(),
    instruction=(
        "You are a Transport Routing Agent. Your job is to suggest routes (Metro, Taxi, Walking, Trains), "
        "estimate costs, and calculate travel times for transfers."
    ),
    tools=[find_routes],
)
