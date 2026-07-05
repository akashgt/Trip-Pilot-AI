from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.genai import types
from database.db_helper import get_hotel, save_hotel, log_audit
import json

def get_hotel_reservation(trip_id: int) -> str:
    """Gets the hotel booking details for a trip.
    
    Args:
        trip_id: Active trip ID.
    """
    hotel = get_hotel(trip_id)
    if hotel:
        return json.dumps(dict(hotel), indent=2)
    return "No hotel records found for this trip."

def reschedule_hotel_checkin(trip_id: int, new_check_in_time: str) -> str:
    """Reschedules the hotel check-in time in database.
    
    Args:
        trip_id: Active trip ID.
        new_check_in_time: The new check-in time or date/time window.
    """
    hotel = get_hotel(trip_id)
    if not hotel:
        return "Error: No hotel reservation found to reschedule."
    
    hotel_dict = dict(hotel)
    old_time = hotel_dict["check_in_time"]
    hotel_dict["check_in_time"] = new_check_in_time
    save_hotel(trip_id, hotel_dict)
    
    log_audit("INFO", "HOTEL_CHECKIN_RESCHEDULED", {
        "trip_id": trip_id,
        "hotel_name": hotel_dict["hotel_name"],
        "old_check_in": old_time,
        "new_check_in": new_check_in_time
    })
    return f"Hotel check-in for '{hotel_dict['hotel_name']}' successfully rescheduled to {new_check_in_time}."

def suggest_nearby_hotels(location: str) -> str:
    """Suggests alternative hotels near the traveler's location.
    
    Args:
        location: Location coordinates or city name (e.g. 'Tokyo Shibuya').
    """
    suggestions = [
        {"hotel_name": "Shibuya Stream Excel Hotel Tokyu", "distance": "0.2 km", "price_per_night": "$220", "rating": "4.6"},
        {"hotel_name": "Cerulean Tower Tokyu Hotel", "distance": "0.5 km", "price_per_night": "$380", "rating": "4.8"},
        {"hotel_name": "The Millennial Shibuya (Cheaper alternative)", "distance": "0.3 km", "price_per_night": "$90", "rating": "4.4"}
    ]
    return json.dumps(suggestions, indent=2)

def get_gemini_model():
    from app.config import config
    return Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    )

hotel_agent = LlmAgent(
    name="hotel_agent",
    description="Manages hotel reservations, check-in updates, and search suggestions.",
    model=get_gemini_model(),
    instruction=(
        "You are a Hotel Management Agent. Your job is to check hotel reservations, "
        "reschedule check-in times when delays occur, and suggest nearby hotels."
    ),
    tools=[get_hotel_reservation, reschedule_hotel_checkin, suggest_nearby_hotels],
)
