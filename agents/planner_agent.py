from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.genai import types
from database.db_helper import (
    get_itinerary, save_itinerary, log_audit,
    save_flight, save_hotel, add_expense, get_active_trip
)
import json

def book_initial_flight_and_hotel(trip_id: int, start_city: str, destination: str, airline: str, hotel_name: str) -> str:
    """Saves the flight and hotel booking details chosen by the travel agent into the database.
    
    Args:
        trip_id: The active trip ID in database.
        start_city: Departure origin city.
        destination: Arrival target destination.
        airline: Realistic airline chosen for this route (e.g., 'Emirates', 'Biman Bangladesh Airlines', 'IndiGo').
        hotel_name: Realistic hotel chosen in target destination (e.g., 'InterContinental Dhaka', 'Taj Exotica Goa').
    """
    import datetime
    trip = get_active_trip("user_1")
    start_date = trip["start_date"] if trip else datetime.date.today().isoformat()
    
    # Dynamic route correction for Jerusalem/Tel Aviv to Paris
    start_clean = start_city.lower()
    dest_clean = destination.lower()
    if ("jerusalem" in start_clean or "tel aviv" in start_clean or "israel" in start_clean) and ("paris" in dest_clean or "france" in dest_clean):
        airline = "Air France"
            
    default_flight = {
        "flight_number": "AF309" if airline == "Air France" else f"{airline[:2].upper()}309",
        "departure_time": f"{start_date}T11:00:00 (from {start_city})",
        "arrival_time": f"{start_date}T16:00:00 (at {destination})",
        "status": "ON_TIME",
        "delay_minutes": 0,
        "airline": airline
    }
    save_flight(trip_id, default_flight)
    
    default_hotel = {
        "hotel_name": hotel_name,
        "check_in_time": "4:00 PM",
        "check_out_time": "11:00 AM",
        "status": "CONFIRMED"
    }
    save_hotel(trip_id, default_hotel)
    
    # Save expenses dynamically scaled to the trip's custom budget limit
    from database.db_helper import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Clear any initial seeded flight/hotel expenses to prevent duplicates
    cursor.execute("DELETE FROM expenses WHERE trip_id = ? AND category IN ('Flight', 'Hotel')", (trip_id,))
    
    # 2. Fetch the trip's budget limit
    cursor.execute("SELECT budget FROM trips WHERE id = ?", (trip_id,))
    row = cursor.fetchone()
    budget = row["budget"] if row else 3000.0
    
    conn.commit()
    conn.close()
    
    flight_cost = round(budget * 0.3, 2)
    hotel_cost = round(budget * 0.4, 2)
    
    add_expense(trip_id, flight_cost, "Flight", f"Roundtrip flight to {destination} on {airline}", "USD", start_date)
    add_expense(trip_id, hotel_cost, "Hotel", f"Hotel reservation at {hotel_name}", "USD", start_date)
    
    log_audit("INFO", "AGENT_BOOKED_RESERVATIONS", {"trip_id": trip_id, "airline": airline, "hotel": hotel_name})
    return f"Flight on {airline} and hotel reservation at {hotel_name} registered successfully."

def create_itinerary_db(trip_id: int, destination: str, start_date: str, end_date: str, itinerary_json_str: str) -> str:
    """Stores the generated itinerary JSON object into the database.
    
    Args:
        trip_id: Active trip ID.
        destination: City/Country.
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        itinerary_json_str: A stringified JSON representing the day-by-day itinerary.
    """
    try:
        itinerary_data = json.loads(itinerary_json_str)
        save_itinerary(trip_id, itinerary_data)
        
        # Parse and log each activity cost as an individual expense entry!
        # Clear any existing non-flight/non-hotel expenses first to prevent duplicates on regeneration
        from database.db_helper import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM expenses WHERE trip_id = ? AND category NOT IN ('Flight', 'Hotel')", (trip_id,))
        conn.commit()
        conn.close()
        
        # Loop through days and activities
        days_list = itinerary_data.get("days") or itinerary_data.get("itinerary") or []
        for day in days_list:
            day_date = day.get("date", start_date)
            for act in day.get("activities", []):
                cost = float(act.get("cost", 0.0))
                if cost > 0:
                    add_expense(
                        trip_id,
                        cost,
                        "Sightseeing",
                        f"{act.get('title')} - {act.get('description', '')[:50]}",
                        "USD",
                        day_date
                    )
                    
        log_audit("INFO", "ITINERARY_CREATED", {"trip_id": trip_id, "destination": destination})
        return "Itinerary successfully saved to the database."
    except Exception as e:
        return f"Error saving itinerary: {str(e)}"

def update_itinerary_activity(trip_id: int, day_number: int, activity_title: str, new_title: str, new_description: str, new_cost: float) -> str:
    """Modifies a specific activity on a given day of the trip.
    
    Args:
        trip_id: Active trip ID.
        day_number: The day number of the trip (1-indexed).
        activity_title: The current title of the activity to replace/update.
        new_title: The new title for the activity.
        new_description: The updated description.
        new_cost: The updated cost of the activity.
    """
    itinerary = get_itinerary(trip_id)
    if not itinerary:
        return "Error: No itinerary found to update."
    
    updated = False
    for day in itinerary.get("days", []):
        if day["day_number"] == day_number:
            for act in day.get("activities", []):
                if activity_title.lower() in act["title"].lower():
                    act["title"] = new_title
                    act["description"] = new_description
                    act["cost"] = new_cost
                    updated = True
                    break
    
    if updated:
        save_itinerary(trip_id, itinerary)
        log_audit("INFO", "ITINERARY_ACTIVITY_UPDATED", {
            "trip_id": trip_id,
            "day": day_number,
            "original_activity": activity_title,
            "new_activity": new_title
        })
        return f"Activity '{activity_title}' updated to '{new_title}' on Day {day_number}."
    return f"Activity '{activity_title}' not found on Day {day_number}."

def get_gemini_model():
    from app.config import config
    return Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    )

planner_agent = LlmAgent(
    name="planner_agent",
    description="Generates, reads, and dynamically updates travel itineraries.",
    model=get_gemini_model(),
    instruction=(
        "You are a Travel Planner Agent. Your job is to draft initial itineraries based on traveler preferences "
        "and modify activities when schedules change (e.g. flight delays or rain forecast). "
        "You MUST first use the book_initial_flight_and_hotel tool to choose and book a realistic, operating airline "
        "(e.g. Biman Bangladesh for Kolkata to Dhaka; Emirates for US to Dubai; Air France for Jerusalem to Paris) "
        "and a real hotel in the target destination, respecting traveler memory preferences only if they are valid for the route. "
        "Do NOT suggest Middle Eastern airlines like Emirates or Qatar Airways on non-ME routes like Jerusalem to Paris; use Air France instead. "
        "Then, use the create_itinerary_db tool to save the daily plans."
    ),
    tools=[create_itinerary_db, update_itinerary_activity, book_initial_flight_and_hotel],
)
