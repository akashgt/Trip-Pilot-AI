from mcp.server.fastmcp import FastMCP
import os
import json
import datetime
from database.db_helper import log_notification, log_audit

# Initialize the FastMCP server
mcp = FastMCP("TripPilot MCP Server")

# -----------------------------------------------------------------------------
# 1. Calendar MCP Tools
# -----------------------------------------------------------------------------

@mcp.tool()
def calendar_add_trip(trip_id: int, destination: str, start_date: str, end_date: str) -> str:
    """Adds a trip itinerary placeholder to the user's Google Calendar.

    Args:
        trip_id: The ID of the trip in database.
        destination: Trip destination city.
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
    """
    event_details = f"Trip to {destination} from {start_date} to {end_date}."
    log_notification(trip_id, f"Calendar Event Added: {event_details}", "CALENDAR")
    log_audit("INFO", "CALENDAR_EVENT_ADDED", {"trip_id": trip_id, "details": event_details})
    return f"Successfully added trip to {destination} ({start_date} to {end_date}) to user's Google Calendar."

@mcp.tool()
def calendar_list_events(trip_id: int) -> str:
    """Retrieves all calendar events for the scheduled trip dates.

    Args:
        trip_id: The active trip ID.
    """
    events = [
        {"title": "Flight NH206 Departure", "time": "July 10, 11:00 AM"},
        {"title": "Hotel Check-in", "time": "July 10, 4:00 PM"},
        {"title": "Dinner Reservation: Gonpachi", "time": "July 11, 7:00 PM"}
    ]
    return json.dumps(events, indent=2)

# -----------------------------------------------------------------------------
# 2. Weather MCP Tools
# -----------------------------------------------------------------------------

@mcp.tool()
def weather_get_forecast(location: str, date: str) -> str:
    """Gets the weather forecast for a destination.

    Args:
        location: City name.
        date: Target travel date (YYYY-MM-DD).
    """
    # Trigger heavy rain forecast for Tokyo on specific events
    loc = location.lower()
    if "tokyo" in loc and ("11" in date or "heavy_rain" in date):
        forecast = {
            "location": location,
            "date": date,
            "condition": "Heavy Rain / Storm Warning",
            "temperature_c": 19,
            "humidity": 90,
            "rain_probability_pct": 98
        }
    else:
        forecast = {
            "location": location,
            "date": date,
            "condition": "Sunny with light breeze",
            "temperature_c": 27,
            "humidity": 60,
            "rain_probability_pct": 10
        }
    return json.dumps(forecast, indent=2)

# -----------------------------------------------------------------------------
# 3. Google Maps MCP Tools
# -----------------------------------------------------------------------------

@mcp.tool()
def maps_get_directions(origin: str, destination: str, mode: str = "transit") -> str:
    """Gets directions, travel time, and distance between two locations.

    Args:
        origin: Start location.
        destination: Destination location.
        mode: Transit mode: 'transit' (train/subway), 'driving' (taxi/uber), or 'walking'.
    """
    routes = {
        "transit": {"duration": "18 mins", "distance": "5.4 km", "cost": "$2.10", "route": "Yamanote Line"},
        "driving": {"duration": "14 mins", "distance": "6.0 km", "cost": "$25.00", "route": "Expressway Route 4"},
        "walking": {"duration": "55 mins", "distance": "4.2 km", "cost": "$0.00", "route": "Direct pedestrian paths"}
    }
    selected = routes.get(mode.lower(), routes["transit"])
    return json.dumps({
        "origin": origin,
        "destination": destination,
        "mode": mode,
        "travel_time": selected["duration"],
        "distance": selected["distance"],
        "estimated_cost_usd": selected["cost"],
        "recommended_route": selected["route"]
    }, indent=2)

@mcp.tool()
def maps_get_nearby_attractions(location: str, category: str = "sightseeing") -> str:
    """Queries Google Maps for top-rated attractions, restaurants, or transit hubs.

    Args:
        location: City/Neighborhood coordinates or name (e.g. 'Tokyo Shibuya').
        category: 'sightseeing', 'dining', or 'transit'.
    """
    loc = location.lower()
    cat = category.lower()
    
    if "tokyo" in loc:
        if "dining" in cat:
            results = [
                {"name": "Gonpachi Nishiazabu (Kill Bill Restaurant)", "rating": "4.3", "price": "$$$", "cuisine": "Izakaya"},
                {"name": "Ichiran Ramen Shibuya", "rating": "4.5", "price": "$", "cuisine": "Ramen"},
                {"name": "Kanda Matsuya (Historic Soba)", "rating": "4.4", "price": "$$", "cuisine": "Soba"}
            ]
        elif "transit" in cat:
            results = [
                {"name": "Shibuya Station (JR & Metro)", "lines": "Yamanote, Ginza, Hanzomon, Fukutoshin"},
                {"name": "Shinjuku Station (World's busiest)", "lines": "JR Yamanote, Chuo, Oedo, Shinjuku Lines"}
            ]
        else: # sightseeing
            results = [
                {"name": "Shibuya Crossing & Hachiko Statue", "rating": "4.6", "type": "Landmark"},
                {"name": "Meiji Jingu Shrine", "rating": "4.7", "type": "Shinto Shrine / Forest Walk"},
                {"name": "Shinjuku Gyoen National Garden", "rating": "4.7", "type": "Botanical Garden"}
            ]
    else:
        results = [{"name": f"Local Attraction in {location}", "rating": "4.5", "type": "Generic"}]
        
    return json.dumps(results, indent=2)

# -----------------------------------------------------------------------------
# 4. Filesystem MCP Tools
# -----------------------------------------------------------------------------

@mcp.tool()
def fs_save_itinerary(trip_id: int, content: str) -> str:
    """Saves a textual copy of the traveler's itinerary to the local file system.

    Args:
        trip_id: The ID of the active trip.
        content: Textual content of the itinerary.
    """
    # Define file path
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    filename = f"itinerary_trip_{trip_id}.txt"
    filepath = os.path.join(base_dir, filename)
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        log_audit("INFO", "FILESYSTEM_ITINERARY_SAVED", {"trip_id": trip_id, "filepath": filepath})
        return f"Successfully saved itinerary to local file system: {filepath}"
    except Exception as e:
        return f"Error saving to filesystem: {str(e)}"

@mcp.tool()
def fs_export_offline(trip_id: int, format_type: str = "TXT") -> str:
    """Exports a mobile-compatible offline trip packet.

    Args:
        trip_id: Active trip ID.
        format_type: Format to export: 'TXT' or 'JSON' or 'PDF'.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    filename = f"offline_packet_{trip_id}.{format_type.lower()}"
    filepath = os.path.join(base_dir, filename)
    
    packet_data = {
        "export_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "trip_id": trip_id,
        "format": format_type,
        "status": "Ready for Offline Access"
    }
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            if format_type.upper() == "JSON":
                json.dump(packet_data, f, indent=2)
            else:
                f.write(f"=== OFFLINE TRIP PACKET ===\nTrip ID: {trip_id}\nStatus: {packet_data['status']}\nExported: {packet_data['export_date']}")
        log_audit("INFO", "FILESYSTEM_OFFLINE_EXPORTED", {"trip_id": trip_id, "filepath": filepath})
        return f"Successfully exported offline {format_type} packet to: {filepath}"
    except Exception as e:
        return f"Error exporting offline packet: {str(e)}"

# -----------------------------------------------------------------------------
# 5. Email MCP Tools
# -----------------------------------------------------------------------------

@mcp.tool()
def email_send_alert(trip_id: int, recipient: str, subject: str, message: str) -> str:
    """Sends a simulated email alert regarding booking changes, flight updates, or safety.

    Args:
        trip_id: Active trip ID.
        recipient: Email address of recipient.
        subject: Email subject line.
        message: Body of the email message.
    """
    email_log = f"Email to {recipient}\nSubject: {subject}\nMessage: {message}"
    log_notification(trip_id, email_log, "EMAIL")
    log_audit("INFO", "EMAIL_ALERT_SENT", {"trip_id": trip_id, "recipient": recipient, "subject": subject})
    return f"Simulated email alert dispatched to {recipient}."

if __name__ == "__main__":
    mcp.run()
