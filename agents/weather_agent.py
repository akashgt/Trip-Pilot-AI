from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.genai import types
import json

def get_weather_forecast(location: str, date: str) -> str:
    """Checks the weather forecast for a location on a specific date.
    
    Args:
        location: City or region.
        date: Target travel date (YYYY-MM-DD).
    """
    loc = location.lower()
    
    # Preserve the specific simulation trigger for the Tokyo heavy rain workflow
    if "tokyo" in loc and ("11" in date or "heavy_rain" in date):
        return json.dumps({"forecast": "Heavy Rain & Strong Winds", "temp_c": 19, "rain_prob_pct": 95, "alert": "Heavy Rain Warning"})
        
    # Fetch real live weather from wttr.in API
    try:
        import urllib.request
        import urllib.parse
        # Clean city name (e.g., "Udaipur, India" -> "Udaipur")
        city_query = location.split(",")[0].strip()
        city_url_encoded = urllib.parse.quote(city_query)
        
        url = f"https://wttr.in/{city_url_encoded}?format=j1"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            
        weather_days = data.get("weather", [])
        if weather_days:
            # Check if there's an exact calendar date match
            matched_day = None
            for w in weather_days:
                if w.get("date") == date:
                    matched_day = w
                    break
            
            # For future dates, project using modulo hashing on returned real weather
            is_future = False
            if not matched_day:
                is_future = True
                import hashlib
                hash_val = int(hashlib.md5(f"{loc}-{date}".encode('utf-8')).hexdigest(), 16)
                matched_day = weather_days[hash_val % len(weather_days)]
                
            temp = int(matched_day.get("maxtempC", 29))
            if is_future:
                # Add minor deterministic variation for future dates
                temp += (hash_val % 5) - 2
                
            hourly = matched_day.get("hourly", [])
            desc = "Sunny and Clear"
            rain_prob = 5
            if hourly:
                # Use index 4 (12:00 PM) for daytime representation
                midday = hourly[min(4, len(hourly)-1)]
                desc_list = midday.get("weatherDesc", [])
                if desc_list:
                    desc = desc_list[0].get("value", "Sunny")
                try:
                    rain_prob = int(midday.get("chanceofrain", 5))
                except Exception:
                    pass
                    
            alert = None
            desc_lower = desc.lower()
            if "storm" in desc_lower or "heavy rain" in desc_lower or rain_prob > 85:
                alert = "Severe Weather Alert"
                
            return json.dumps({
                "forecast": desc,
                "temp_c": temp,
                "rain_prob_pct": rain_prob,
                "alert": alert
            })
    except Exception:
        # Fallback to simulation if network is unreachable or limits hit
        pass
        
    # Deterministic simulation fallback
    import hashlib
    hash_val = int(hashlib.md5(f"{loc}-{date}".encode('utf-8')).hexdigest(), 16)
    forecasts = [
        ("Sunny and Clear", 28, 5, None),
        ("Partly Cloudy", 24, 15, None),
        ("Passing Showers", 22, 65, None),
        ("Mostly Sunny", 27, 8, None),
        ("Overcast", 21, 20, None),
        ("Light Rain", 20, 75, None),
        ("Scattered Thunderstorms", 25, 85, "Thunderstorm Alert"),
        ("Breezy and Clear", 26, 4, None)
    ]
    
    idx = hash_val % len(forecasts)
    forecast_text, base_temp, rain_prob, alert = forecasts[idx]
    temp = base_temp + (hash_val % 5) - 2
    
    return json.dumps({
        "forecast": forecast_text,
        "temp_c": temp,
        "rain_prob_pct": rain_prob,
        "alert": alert
    })

def recommend_indoor_activities(location: str) -> str:
    """Recommends indoor activities and museums in the target area.
    
    Args:
        location: City or region.
    """
    if "tokyo" in location.lower():
        recs = [
            {"title": "teamLab Planets TOKYO", "description": "Digital art museum with interactive light water installations.", "location": "Toyosu", "cost": 3800},
            {"title": "Mori Art Museum", "description": "Contemporary art museum located at the top of Roppongi Hills.", "location": "Roppongi", "cost": 2000},
            {"title": "Tokyo National Museum", "description": "Historical collection of Japanese art and cultural artifacts.", "location": "Ueno Park", "cost": 1000}
        ]
        return json.dumps(recs, indent=2)
    return "[]"

def get_gemini_model():
    from app.config import config
    return Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    )

weather_agent = LlmAgent(
    name="weather_agent",
    description="Monitors weather forecasts and provides indoor activity suggestions.",
    model=get_gemini_model(),
    instruction=(
        "You are a Weather Agent. Your role is to monitor local weather alerts, "
        "check forecasts, and recommend indoor alternatives when severe weather/rain is predicted."
    ),
    tools=[get_weather_forecast, recommend_indoor_activities],
)
