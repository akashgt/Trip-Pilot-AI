from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.genai import types
from database.db_helper import get_user_preferences, update_user_preferences, log_audit
import json

def load_preferences(user_id: str) -> str:
    """Loads traveler preferences and history from the database.
    
    Args:
        user_id: Unique identifier for the traveler (e.g. 'user_1').
    """
    prefs = get_user_preferences(user_id)
    log_audit("INFO", "LOAD_PREFERENCES", {"user_id": user_id})
    return json.dumps(prefs, indent=2)

def save_preferences(user_id: str, favorite_airlines: list, favorite_hotels: list, preferred_transport: str, food_restrictions: list) -> str:
    """Saves/Updates traveler preferences in the database.
    
    Args:
        user_id: Unique identifier of the traveler.
        favorite_airlines: List of preferred airlines (e.g., ['ANA', 'JAL']).
        favorite_hotels: List of preferred hotel chains.
        preferred_transport: Default transit method (Metro, Taxi, Walking).
        food_restrictions: List of food allergies or diet constraints.
    """
    prefs = {
        "user_id": user_id,
        "favorite_airlines": favorite_airlines,
        "favorite_hotels": favorite_hotels,
        "preferred_transport": preferred_transport,
        "food_restrictions": food_restrictions,
        "preferred_language": "English",
        "visa_status": "Visa Free / 90 Days",
        "frequent_flyer_number": "JAL-889104"
    }
    update_user_preferences(prefs)
    log_audit("INFO", "UPDATE_PREFERENCES", {"user_id": user_id, "prefs": prefs})
    return "User preferences updated successfully."

def get_gemini_model():
    from app.config import config
    return Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    )

memory_agent = LlmAgent(
    name="memory_agent",
    description="Loads and updates user flight, hotel, transit, and food preferences.",
    model=get_gemini_model(),
    instruction=(
        "You are a Traveler Memory Agent. Your job is to fetch and record preferences for the traveler. "
        "Use load_preferences to read preferences and save_preferences to store them. "
        "Always tailor plan considerations (e.g. seat choices, transport modes) based on the user's history."
    ),
    tools=[load_preferences, save_preferences],
)
