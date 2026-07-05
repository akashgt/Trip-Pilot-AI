from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.genai import types
import json

def lookup_emergency_contacts(location: str) -> str:
    """Finds nearest hospitals, police stations, and embassies for a travel city.
    
    Args:
        location: Target city (e.g. 'Tokyo').
    """
    loc = location.lower()
    if "tokyo" in loc or "japan" in loc:
        contacts = {
            "embassy": "U.S. Embassy Tokyo: 1-10-5 Akasaka, Minato-ku, Tel: +81 3-3224-5000",
            "police": "Emergency Police: dial 110 (English support available)",
            "hospital": "St. Luke's International Hospital: 9-1 Akashicho, Chuo-ku, Tel: +81 3-3541-5151",
            "fire_ambulance": "Fire & Ambulance: dial 119"
        }
    elif "india" in loc or any(city in loc for city in ["goa", "mumbai", "delhi", "bengaluru", "bangalore", "jaipur", "chennai", "kolkata", "pune", "hyderabad", "kochi", "agra"]):
        contacts = {
            "embassy": "U.S. Embassy New Delhi: Shantipath, Chanakyapuri, New Delhi, Tel: +91 11-2419-8000",
            "police": "Emergency Police: dial 112 / 100",
            "hospital": "Fortis / Apollo Emergency Care (Ambulance: dial 102 or 108)",
            "fire_ambulance": "Fire: dial 101 / Ambulance: dial 102 or 108"
        }
    else:
        contacts = {
            "embassy": f"Local Consulate/Embassy in {location}",
            "police": "Police: dial 911 / 112 (local emergency)",
            "hospital": f"General Hospital in {location}",
            "fire_ambulance": "Emergency Services: Dial local fire department"
        }
    return json.dumps(contacts, indent=2)

def get_lost_passport_checklist() -> str:
    """Returns the official step-by-step checklist for replacing a lost or stolen passport while abroad."""
    checklist = [
        "Step 1: File a police report at the nearest local police station and obtain a copy.",
        "Step 2: Take new passport photos (standard 2x2 inches format).",
        "Step 3: Locate and visit the nearest national Embassy or Consulate.",
        "Step 4: Fill out forms DS-11 (Application for Passport) and DS-64 (Statement of Lost/Stolen Passport).",
        "Step 5: Present proof of identity, travel tickets/itinerary, and pay the replacement fee.",
        "Step 6: Receive an emergency temporary passport to return home."
    ]
    return json.dumps(checklist, indent=2)

def get_gemini_model():
    from app.config import config
    return Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    )

emergency_agent = LlmAgent(
    name="emergency_agent",
    description="Provides emergency medical contacts, embassy numbers, and lost passport workflows.",
    model=get_gemini_model(),
    instruction=(
        "You are an Emergency Assistant Agent. Your role is to look up emergency services, "
        "nearest embassies, and explain the procedure to replace a lost passport abroad."
    ),
    tools=[lookup_emergency_contacts, get_lost_passport_checklist],
)
