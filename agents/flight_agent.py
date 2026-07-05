from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.genai import types
from database.db_helper import get_flight, save_flight, log_audit
import json

def get_flight_status(trip_id: int) -> str:
    """Gets current flight booking and delay status for a trip.
    
    Args:
        trip_id: The active trip ID.
    """
    flight = get_flight(trip_id)
    if flight:
        return json.dumps(dict(flight), indent=2)
    return "No flight records found for this trip."

def update_flight_delay(trip_id: int, delay_minutes: int, reason: str) -> str:
    """Updates the flight delay in the database and marks it delayed.
    
    Args:
        trip_id: The active trip ID.
        delay_minutes: Minutes of delay.
        reason: Reason for the flight delay.
    """
    flight = get_flight(trip_id)
    if not flight:
        return "Error: No flight record exists to update."
    
    flight_dict = dict(flight)
    flight_dict["status"] = "DELAYED"
    flight_dict["delay_minutes"] = delay_minutes
    # Adjust arrival time (simulated)
    import datetime
    try:
        arr_time = datetime.datetime.fromisoformat(flight_dict["arrival_time"])
        new_arr_time = arr_time + datetime.timedelta(minutes=delay_minutes)
        flight_dict["arrival_time"] = new_arr_time.isoformat()
    except Exception:
        # Fallback if arrival_time is just text
        flight_dict["arrival_time"] = f"{flight_dict['arrival_time']} (+{delay_minutes}m)"

    save_flight(trip_id, flight_dict)
    log_audit("WARNING", "FLIGHT_DELAY_DETECTED", {
        "trip_id": trip_id,
        "flight_number": flight_dict["flight_number"],
        "delay_minutes": delay_minutes,
        "reason": reason
    })
    return f"Flight status updated to DELAYED with a {delay_minutes}-minute delay. New arrival: {flight_dict['arrival_time']}."

def find_alternative_flights(trip_id: int) -> str:
    """Finds alternative flights for the user's flight route in case of cancellations or heavy delays.
    
    Args:
        trip_id: Active trip ID.
    """
    flight = get_flight(trip_id)
    if not flight:
        return "No flight record to search alternatives for."
    
    # Return simulated alternative flights
    alts = [
        {"flight_number": f"{flight['airline'][:2]}209", "departure_time": "3 hours later", "status": "ON_TIME", "airline": flight["airline"]},
        {"flight_number": "JAL402", "departure_time": "5 hours later", "status": "ON_TIME", "airline": "Japan Airlines"}
    ]
    return json.dumps(alts, indent=2)

def get_gemini_model():
    from app.config import config
    return Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    )

flight_agent = LlmAgent(
    name="flight_agent",
    description="Monitors flight details, tracks delays, and searches alternative flights.",
    model=get_gemini_model(),
    instruction=(
        "You are a Flight Monitoring Agent. Your role is to get flight statuses, update delays, "
        "and find alternative flights when needed. Always report status changes clearly."
    ),
    tools=[get_flight_status, update_flight_delay, find_alternative_flights],
)
