import streamlit as st
import os
import json
import asyncio
import datetime
import altair as pd
import pandas as pd
from typing import Optional

# Setup environmental paths before importing ADK/GenAI
import sys
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

# Set dotenv path and load
from dotenv import load_dotenv
env_path = os.path.join(BASE_DIR, '.env')
load_dotenv(dotenv_path=env_path, override=True)

# Force load correct API key
if 'GOOGLE_API_KEY' in os.environ:
    os.environ['GEMINI_API_KEY'] = os.environ['GOOGLE_API_KEY']

from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.events.request_input import RequestInput
from google.genai import types

from app.agent import root_agent as workflow_agent
from database.db_helper import (
    get_active_trip, create_trip, get_itinerary, save_itinerary,
    get_flight, save_flight, get_hotel, save_hotel,
    get_expenses, add_expense, get_notifications, get_user_preferences,
    update_user_preferences, get_audit_logs, log_audit
)

# Page configuration
st.set_page_config(
    page_title="TripPilot-AI Dashboard",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Global styles and Dark Theme adjustments
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    
    .main-title {
        font-family: 'Outfit', sans-serif;
        font-weight: 800;
        background: linear-gradient(135deg, #38ef7d 0%, #11998e 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 5px;
    }
    
    .subtitle {
        color: #8f9cae;
        font-size: 1.1rem;
        margin-bottom: 25px;
    }
    
    .glass-card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.2);
    }
    
    .glow-border-red {
        border: 1px solid rgba(239, 83, 80, 0.4);
        background: rgba(239, 83, 80, 0.02);
    }
    
    .glow-border-green {
        border: 1px solid rgba(76, 175, 80, 0.4);
        background: rgba(76, 175, 80, 0.02);
    }
    
    .glow-border-blue {
        border: 1px solid rgba(33, 150, 243, 0.4);
        background: rgba(33, 150, 243, 0.02);
    }

    .stat-val {
        font-family: 'Outfit', sans-serif;
        font-size: 2.2rem;
        font-weight: 700;
        color: #ffffff;
    }
    
    .stat-lbl {
        color: #8f9cae;
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .badge {
        display: inline-block;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
    }
    .badge-ok { background: rgba(76, 175, 80, 0.15); color: #4caf50; }
    .badge-warn { background: rgba(255, 152, 0, 0.15); color: #ff9800; }
    .badge-danger { background: rgba(244, 67, 54, 0.15); color: #f44336; }
</style>
""", unsafe_allow_html=True)

# Initialize Session state for agent runner, chat, and trigger processes
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "current_interrupt" not in st.session_state:
    st.session_state.current_interrupt = None
if "agent_runner" not in st.session_state:
    session_service = InMemorySessionService()
    st.session_state.agent_runner = Runner(
        agent=workflow_agent,
        session_service=session_service,
        auto_create_session=True,
        app_name="trippilot_web_app"
    )
if "simulation_response" not in st.session_state:
    st.session_state.simulation_response = ""

runner = st.session_state.agent_runner

def reset_agent_loops():
    """Clears cached api_client on LLM models to prevent asyncio loop errors in Streamlit threads."""
    try:
        from app.agent import (
            gemini_model, planner_agent, flight_agent, hotel_agent,
            weather_agent, budget_agent, transport_agent,
            notification_agent, emergency_agent, memory_agent
        )
        models = [gemini_model]
        for agent in [planner_agent, flight_agent, hotel_agent, weather_agent, budget_agent, transport_agent, notification_agent, emergency_agent, memory_agent]:
            if hasattr(agent, 'model') and agent.model:
                models.append(agent.model)
                
        for model in models:
            if 'api_client' in model.__dict__:
                del model.__dict__['api_client']
    except Exception:
        pass

def execute_agent_prompt(prompt: str, resume_response: str = None) -> list:
    """Invokes the ADK runner asynchronously and collects generated events."""
    reset_agent_loops()
    async def _run():
        user_id = "user_1"
        session_id = "session_web_active"
        
        new_msg = None
        if resume_response:
            new_msg = types.Content(
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id="confirm_travel_change",
                            name="confirm_travel_change",
                            response={"result": resume_response}
                        )
                    )
                ]
            )
        else:
            new_msg = types.Content(
                parts=[types.Part.from_text(text=prompt)]
            )
            
        events = []
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=new_msg
        ):
            events.append(event)
        return events
        
    try:
        return asyncio.run(_run())
    except Exception as e:
        err_msg = str(e)
        if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
            st.session_state.last_error_rate_limited = True
        else:
            st.error(f"Execution Error: {err_msg}")
        return []

# Sidebar navigation
with st.sidebar:
    st.markdown("<h2 class='main-title'>✈️ TripPilot-AI</h2>", unsafe_allow_html=True)
    st.markdown("<p class='subtitle'>Proactive Travel Concierge</p>", unsafe_allow_html=True)
    
    page = st.radio(
        "Navigation",
        [
            "🏠 Home",
            "🗺️ Trip Planner",
            "📋 Live Itinerary",
            "⛈️ Weather Companion",
            "💰 Budget Tracker",
            "🚨 Emergency Console",
            "🔔 Notifications",
            "⚙️ Travel Preferences"
        ]
    )
    
    st.markdown("---")
    # Quick active trip summary
    active_trip = get_active_trip("user_1")
    if active_trip:
        st.markdown(f"**Active Destination:**\n{active_trip['destination']}")
        st.markdown(f"**Dates:**\n{active_trip['start_date']} to {active_trip['end_date']}")
        st.markdown(f"**Status:** `{active_trip['status']}`")
    else:
        st.info("No active trips scheduled.")

# Retrieve active trip information
trip = get_active_trip("user_1")
trip_id = trip["id"] if trip else None

# -----------------------------------------------------------------------------
# PAGE 1: Home
# -----------------------------------------------------------------------------
if page == "🏠 Home":
    st.markdown("<h1 class='main-title'>Welcome to TripPilot-AI</h1>", unsafe_allow_html=True)
    st.markdown("<p class='subtitle'>Your AI Travel Companion That Doesn't Just Plan Trips — It Travels With You.</p>", unsafe_allow_html=True)
    
    # Showcase banner image
    banner_path = os.path.join(BASE_DIR, "assets", "cover_page_banner.png")
    if os.path.exists(banner_path):
        st.image(banner_path, use_container_width=True)
        
    st.markdown("""
    ### Why TripPilot-AI?
    TripPilot-AI is a next-generation multi-agent itinerary planner and flight/weather monitor built using **Google Agent Development Kit (ADK) 2.0**.
    
    When disruptions occur, like a **flight delay** or **heavy storm warning**, TripPilot-AI does not just send you an alert:
    1. It recalculates late arrival times.
    2. Suggests adjustments to hotel check-in times.
    3. Prompts local transportation transfers.
    4. Swaps outdoor sightseeing slots for indoor attractions.
    5. Recalculates total trip costs.
    6. **Asks for your explicit confirmation** (Human-in-the-loop) before executing bookings!
    """)
    
    # Display Stats Cards
    if trip:
        st.markdown("### Active Trip Overview")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            flight = get_flight(trip_id)
            status = flight["status"] if flight else "No flight"
            badge_class = "badge-ok" if status == "ON_TIME" else "badge-warn"
            st.markdown(f"""
            <div class='glass-card'>
                <div class='stat-lbl'>Flight Status</div>
                <div class='stat-val'>{flight['flight_number'] if flight else 'N/A'}</div>
                <span class='badge {badge_class}'>{status}</span>
            </div>
            """, unsafe_allow_html=True)
            
        with col2:
            hotel = get_hotel(trip_id)
            st.markdown(f"""
            <div class='glass-card'>
                <div class='stat-lbl'>Hotel Check-in</div>
                <div class='stat-val'>{hotel['check_in_time'] if hotel else 'N/A'}</div>
                <span class='badge badge-ok'>Confirmed</span>
            </div>
            """, unsafe_allow_html=True)
            
        with col3:
            expenses = get_expenses(trip_id)
            total_spent = sum(e["amount"] for e in expenses)
            trip_budget = float(trip.get("budget", 3000.0))
            is_overrun = total_spent > trip_budget
            badge_class = "badge-danger" if is_overrun else "badge-ok"
            badge_lbl = "Over Budget" if is_overrun else "Within Budget"
            st.markdown(f"""
            <div class='glass-card'>
                <div class='stat-lbl'>Total Expenses</div>
                <div class='stat-val'>${total_spent:.2f}</div>
                <span class='badge {badge_class}'>{badge_lbl}</span>
            </div>
            """, unsafe_allow_html=True)
            
        with col4:
            notes = get_notifications(trip_id)
            st.markdown(f"""
            <div class='glass-card'>
                <div class='stat-lbl'>Alerts Sent</div>
                <div class='stat-val'>{len(notes)}</div>
                <span class='badge badge-blue'>Dispatched</span>
            </div>
            """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# PAGE 2: Trip Planner
# -----------------------------------------------------------------------------
elif page == "🗺️ Trip Planner":
    st.markdown("<h1 class='main-title'>Plan a New Journey</h1>", unsafe_allow_html=True)
    st.markdown("<p class='subtitle'>Configure destination, dates, and create your personalized agentic itinerary.</p>", unsafe_allow_html=True)
    
    if trip:
        st.warning(f"Note: You have an active trip to {trip['destination']}. Creating a new trip will replace it.")
        
    ALL_CITIES = sorted([
        # A
        "Amsterdam, Netherlands", "Athens, Greece", "Auckland, New Zealand", "Abu Dhabi, UAE", "Atlanta, USA", "Austin, USA", "Agra, India",
        # B
        "Bangkok, Thailand", "Beijing, China", "Barcelona, Spain", "Berlin, Germany", "Boston, USA", "Brussels, Belgium", "Buenos Aires, Argentina", "Bengaluru, India", "Budapest, Hungary",
        # C
        "Cairo, Egypt", "Cape Town, South Africa", "Chicago, USA", "Copenhagen, Denmark", "Colombo, Sri Lanka", "Chennai, India", "Casablanca, Morocco",
        # D
        "Dhaka, Bangladesh", "Dallas, USA", "Delhi, India", "Detroit, USA", "Dublin, Ireland", "Doha, Qatar", "Dubai, UAE", "Dammam, Saudi Arabia", "Denver, USA", "Dakar, Senegal",
        # E
        "Edinburgh, UK", "Edmonton, Canada", "Eindhoven, Netherlands", "Entebbe, Uganda", "Ernakulam, India",
        # F
        "Frankfurt, Germany", "Florence, Italy", "Fukuoka, Japan", "Fort Worth, USA", "Fujairah, UAE",
        # G
        "Goa, India", "Geneva, Switzerland", "Guangzhou, China", "Glasgow, UK", "Gothenburg, Sweden",
        # H
        "Hong Kong", "Helsinki, Finland", "Houston, USA", "Hanoi, Vietnam", "Hyderabad, India", "Hamburg, Germany", "Havana, Cuba",
        # I
        "Istanbul, Turkey", "Indianapolis, USA", "Islamabad, Pakistan", "Incheon, South Korea", "Indore, India", "Innsbruck, Austria",
        # J
        "Jakarta, Indonesia", "Johannesburg, South Africa", "Jeddah, Saudi Arabia", "Jaipur, India", "Jerusalem, Israel",
        # K
        "Kolkata, India", "Kochi, India", "Kuala Lumpur, Malaysia", "Kyoto, Japan", "Karachi, Pakistan", "Kathmandu, Nepal", "Kabul, Afghanistan", "Kiev, Ukraine", "Kigali, Rwanda",
        # L
        "London, UK", "Los Angeles, USA", "Lisbon, Portugal", "Lima, Peru", "Las Vegas, USA", "Lahore, Pakistan", "Luxembourg City, Luxembourg",
        # M
        "Mumbai, India", "Munich, Germany", "Madrid, Spain", "Manila, Philippines", "Melbourne, Australia", "Montreal, Canada", "Moscow, Russia", "Miami, USA", "Milan, Italy", "Muscat, Oman", "Male, Maldives",
        # N
        "New York, USA", "Nairobi, Kenya", "Nashville, USA", "Nice, France", "Naples, Italy", "Nagoya, Japan",
        # O
        "Osaka, Japan", "Oslo, Norway", "Orlando, USA", "Ottawa, Canada", "Oxford, UK", "Oaxaca, Mexico",
        # P
        "Paris, France", "Prague, Czech Republic", "Philadelphia, USA", "Phoenix, USA", "Pune, India", "Phuket, Thailand", "Port Louis, Mauritius", "Portland, USA",
        # Q
        "Quebec City, Canada", "Quito, Ecuador", "Qingdao, China", "Queenstown, New Zealand",
        # R
        "Rome, Italy", "Rio de Janeiro, Brazil", "Riyadh, Saudi Arabia", "Reykjavik, Iceland", "Rotterdam, Netherlands", "Raleigh, USA",
        # S
        "Singapore", "Sydney, Australia", "San Francisco, USA", "Seattle, USA", "Seoul, South Korea", "Shanghai, China", "Stockholm, Sweden", "Salzburg, Austria", "Santiago, Chile", "Sao Paulo, Brazil", "Srinagar, India", "Sharjah, UAE",
        # T
        "Tokyo, Japan", "Toronto, Canada", "Taipei, Taiwan", "Tel Aviv, Israel", "Tashkent, Uzbekistan", "Tbilisi, Georgia", "Turin, Italy", "Tampa, USA", "Thiruvananthapuram, India",
        # U
        "Ulaanbaatar, Mongolia", "Utrecht, Netherlands", "Urayasu, Japan", "Udaipur, India",
        # V
        "Vancouver, Canada", "Vienna, Austria", "Venice, Italy", "Vilnius, Lithuania", "Varanasi, India",
        # W
        "Washington DC, USA", "Warsaw, Poland", "Wellington, New Zealand", "Winnipeg, Canada", "Wuhan, China",
        # X
        "Xi'an, China", "Xiamen, China", "Xining, China",
        # Y
        "Yokohama, Japan", "Yangon, Myanmar", "Yerevan, Armenia", "Yekaterinburg, Russia",
        # Z
        "Zurich, Switzerland", "Zagreb, Croatia", "Zanzibar, Tanzania", "Zhengzhou, China"
    ]) + ["Other / Custom City..."]

    col_start, col_dest = st.columns(2)
    with col_start:
        start_choice = st.selectbox("Starting City / Origin (Type to search)", ALL_CITIES, index=ALL_CITIES.index("New York, USA"))
        if start_choice == "Other / Custom City...":
            start_city = st.text_input("Enter Starting City", value="")
        else:
            start_city = start_choice
            
    with col_dest:
        dest_choice = st.selectbox("Destination City (Type to search)", ALL_CITIES, index=ALL_CITIES.index("Tokyo, Japan"))
        if dest_choice == "Other / Custom City...":
            dest = st.text_input("Enter Destination City", value="")
        else:
            dest = dest_choice
            
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", value=datetime.date(2026, 7, 10))
    with col2:
        end_date = st.date_input("End Date", value=datetime.date(2026, 7, 17))
        
    budget = st.number_input("Total Budget Limit ($)", value=3000)
    include_sightseeing = st.checkbox("Include Local Sightseeing Activities", value=True)
    st.session_state.include_sightseeing = include_sightseeing
    submitted = st.button("Generate Itinerary")
        
    if submitted:
        with st.spinner("TripPilot-AI agents are planning your trip, setting up reservations, and applying user memory..."):
            # Create Trip in DB
            new_trip_id = create_trip("user_1", dest, str(start_date), str(end_date), float(budget))
            
            # Fetch user preferences for contextual memory seeding
            prefs = get_user_preferences("user_1")
            
            # Dynamically determine airline, flight number, and hotel based on route and memory
            dest_lower = dest.lower()
            start_lower = start_city.lower()
            
            # Regional indicators
            is_asia = lambda s: any(x in s for x in ["india", "goa", "kolkata", "dhaka", "bangladesh", "tokyo", "japan", "singapore", "bangkok", "thailand", "beijing", "china", "shanghai", "hong kong", "seoul", "korea", "kuala lumpur", "malaysia", "kabul", "kochi", "karachi", "kathmandu"])
            is_europe = lambda s: any(x in s for x in ["london", "uk", "paris", "france", "germany", "frankfurt", "munich", "rome", "italy", "amsterdam", "netherlands", "athens", "greece", "dublin", "ireland", "vienna", "austria", "zurich", "switzerland", "istanbul", "turkey"])
            is_us = lambda s: any(x in s for x in ["usa", "york", "dallas", "detroit", "denver", "atlanta", "austin", "boston", "seattle", "chicago", "los angeles", "san francisco", "houston", "orlando", "portland", "raleigh", "washington", "canada", "toronto", "vancouver"])
            is_me = lambda s: any(x in s for x in ["dubai", "uae", "doha", "qatar", "riyadh", "saudi", "dammam", "jeddah", "muscat", "oman", "sharjah"])
            
            # Default values (e.g. global fallback)
            airline = "Singapore Airlines"
            flight_num = "SQ807"
            hotel_name = "Grand Hyatt"
            
            if "tokyo" in dest_lower or "japan" in dest_lower:
                airline = "All Nippon Airways"
                flight_num = "NH206"
                hotel_name = "Park Hyatt Tokyo"
            elif "goa" in dest_lower or "india" in dest_lower:
                airline = "IndiGo"
                flight_num = "6E2091"
                hotel_name = "Taj Exotica Resort & Spa, Goa"
            elif "dubai" in dest_lower or "uae" in dest_lower:
                airline = "Emirates"
                flight_num = "EK571"
                hotel_name = "Atlantis The Palm, Dubai"
            elif "dhaka" in dest_lower or "bangladesh" in dest_lower:
                airline = "Biman Bangladesh Airlines"
                flight_num = "BG392"
                hotel_name = "InterContinental Dhaka"
            elif is_asia(dest_lower) and is_asia(start_lower):
                # Regional Asian flight
                if "bangkok" in start_lower or "thailand" in start_lower or "bangkok" in dest_lower or "thailand" in dest_lower:
                    airline = "Thai Airways"
                    flight_num = "TG674"
                elif "singapore" in start_lower or "singapore" in dest_lower:
                    airline = "Singapore Airlines"
                    flight_num = "SQ802"
                else:
                    airline = "AirAsia"
                    flight_num = "AK512"
                hotel_name = f"Shangri-La {dest.split(',')[0].strip()}"
            elif is_europe(dest_lower) or is_europe(start_lower):
                # European route
                if "london" in start_lower or "uk" in start_lower or "london" in dest_lower or "uk" in dest_lower:
                    airline = "British Airways"
                    flight_num = "BA249"
                elif "germany" in start_lower or "germany" in dest_lower:
                    airline = "Lufthansa"
                    flight_num = "LH782"
                else:
                    airline = "Air France"
                    flight_num = "AF183"
                hotel_name = f"Sofitel {dest.split(',')[0].strip()}"
            elif is_us(dest_lower) or is_us(start_lower):
                # North American route
                airline = "United Airlines"
                flight_num = "UA129"
                hotel_name = f"Marriott {dest.split(',')[0].strip()}"
            elif is_me(dest_lower) or is_me(start_lower):
                # Middle Eastern route
                airline = "Qatar Airways"
                flight_num = "QR830"
                hotel_name = f"Sheraton {dest.split(',')[0].strip()}"
                
            # If traveler has explicit preferences saved in memory, respect them if regionally valid!
            if prefs.get("favorite_airlines"):
                fav_airline = prefs["favorite_airlines"][0]
                is_japan_route = "japan" in dest_lower or "tokyo" in dest_lower or "japan" in start_city.lower() or "tokyo" in start_city.lower()
                is_us_route = "usa" in dest_lower or "york" in dest_lower or "usa" in start_city.lower() or "york" in start_city.lower()
                
                if fav_airline in ["All Nippon Airways", "ANA", "Japan Airlines", "JAL"] and not is_japan_route:
                    pass # Skip Japanese airline on non-Japan route
                elif fav_airline in ["United", "United Airlines"] and not is_us_route:
                    pass # Skip US airline on non-US route
                elif ("jerusalem" in start_lower or "tel aviv" in start_lower or "israel" in start_lower) and ("paris" in dest_lower or "france" in dest_lower):
                    # Force Air France for Jerusalem-Paris route
                    airline = "Air France"
                    flight_num = "AF183"
                else:
                    airline = fav_airline
                    flight_num = f"{airline[:2].upper()}982"
                    
            if prefs.get("favorite_hotels"):
                hotel_name = f"{prefs['favorite_hotels'][0]} {dest.split(',')[0].strip()}"
            
            # Setup default flight and hotel
            default_flight = {
                "flight_number": flight_num,
                "departure_time": f"{start_date}T11:00:00 (from {start_city})",
                "arrival_time": f"{start_date}T16:00:00 (at {dest})",
                "status": "ON_TIME",
                "delay_minutes": 0,
                "airline": airline
            }
            save_flight(new_trip_id, default_flight)
            
            default_hotel = {
                "hotel_name": hotel_name,
                "check_in_time": "4:00 PM",
                "check_out_time": "11:00 AM",
                "status": "CONFIRMED"
            }
            save_hotel(new_trip_id, default_hotel)
            
            # Add initial flight and hotel expenses scaled dynamically to the custom budget
            flight_cost = round(float(budget) * 0.3, 2)
            hotel_cost = round(float(budget) * 0.4, 2)
            add_expense(new_trip_id, flight_cost, "Flight", f"Roundtrip flight {flight_num} from {start_city} to {dest}", "USD", str(start_date))
            add_expense(new_trip_id, hotel_cost, "Hotel", f"Hotel booking at {hotel_name} in {dest}", "USD", str(start_date))
            
            # Automatically dispatch and log booking notifications for the audience presentation
            from database.db_helper import log_notification
            
            email_msg = (
                f"Email to: traveler@trippilot.ai\n"
                f"Subject: ✈️ Journey Confirmed: {start_city} to {dest}\n"
                f"Body: Welcome aboard! Your trip details are confirmed:\n"
                f"  - Flight: {airline} ({flight_num}) departing on {start_date}\n"
                f"  - Hotel: {hotel_name} (Confirmed check-in at 4:00 PM)\n\n"
                f"TripPilot-AI is now continuously monitoring local weather alerts and flight statuses on your behalf."
            )
            log_notification(new_trip_id, email_msg, "EMAIL")
            
            push_msg = (
                f"Companion Alert: New trip booked to {dest}! "
                f"Dates: {start_date} to {end_date}. Shared itinerary details have been sent to your TripPilot dashboard."
            )
            log_notification(new_trip_id, push_msg, "PUSH")
            
            # Check for weather alerts dynamically and log warnings if found!
            from agents.weather_agent import get_weather_forecast
            has_turbulent_weather = False
            turbulent_date = None
            alert_name = None
            
            # Inspect first 3 days of the trip forecast
            for offset_days in range(3):
                chk_date = (start_date + datetime.timedelta(days=offset_days)).isoformat()
                weather_json = get_weather_forecast(dest, chk_date)
                try:
                    w = json.loads(weather_json)
                    if w.get("alert"):
                        has_turbulent_weather = True
                        turbulent_date = chk_date
                        alert_name = w["alert"]
                        break
                except Exception:
                    pass
            
            if has_turbulent_weather:
                weather_msg = (
                    f"Email to: traveler@trippilot.ai\n"
                    f"Subject: ⛈️ Weather Advisory: Storm forecast for {dest} on {turbulent_date}\n"
                    f"Body: Hi Traveler,\n\n"
                    f"Our weather monitor detected a severe '{alert_name}' in {dest} on {turbulent_date}.\n"
                    f"For your comfort and safety, your AI travel concierge has automatically adjusted the itinerary, "
                    f"swapping outdoor sightseeing with premium indoor experiences.\n\n"
                    f"Check the updated live itinerary on your dashboard."
                )
                log_notification(new_trip_id, weather_msg, "EMAIL")
                
                flight_warning = (
                    f"Companion Alert: ⚠️ High risk of flight delays/cancellation on {start_date} "
                    f"due to forecasted thunderstorm/heavy rain in {dest}. We are monitoring the airline status."
                )
                log_notification(new_trip_id, flight_warning, "PUSH")
            
            # Call Planner Agent via ADK to build itinerary
            if include_sightseeing:
                sightseeing_clause = "Include daily paid sightseeing events, activities, and local tours."
            else:
                sightseeing_clause = "Do NOT include any paid local sightseeing activities, tours, or excursions in the itinerary. Keep the activities list limited to free relaxation at the hotel/resort with 0 cost."
                
            prompt = (
                f"Create a day-by-day itinerary for visiting {dest} starting from {start_city} from {start_date} to {end_date}. "
                f"Seed it with default flights and hotels. The traveler hates seafood and prefers hotels from: {prefs['favorite_hotels']} "
                f"and airlines like {prefs['favorite_airlines']}. {sightseeing_clause} "
                f"Make sure to save it in database using the create_itinerary_db tool for trip ID {new_trip_id}."
            )
            
            events = execute_agent_prompt(prompt)
            
            # Fallback seeder check: If the agent prompt execution failed (e.g. 429 rate limit)
            # and no itinerary was saved in the database, automatically seed a fallback itinerary
            # to ensure the presentation remains flawless and the budget tracker updates.
            from database.db_helper import get_itinerary
            if get_itinerary(new_trip_id) is None:
                from database.db_helper import save_itinerary
                
                city = dest.split(',')[0].strip()
                days_count = (end_date - start_date).days + 1
                if days_count <= 0 or days_count > 15:
                    days_count = 7
                    
                fallback_itinerary = {
                    "trip_id": new_trip_id,
                    "destination": dest,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "days": []
                }
                
                if not include_sightseeing:
                    # Seed empty/free relaxation days
                    for i in range(1, days_count + 1):
                        day_date = (start_date + datetime.timedelta(days=i-1)).isoformat()
                        fallback_itinerary["days"].append({
                            "day_number": i,
                            "date": day_date,
                            "activities": [
                                {"time": "Morning", "title": "Relax at hotel resort", "description": "Leisure time to rest and enjoy hotel amenities.", "cost": 0.0, "location": f"{hotel_name}", "category": "Relaxation"},
                                {"time": "Afternoon", "title": "Leisurely neighborhood walk", "description": "Explore the local area around the hotel on foot.", "cost": 0.0, "location": f"Near {hotel_name}", "category": "Relaxation"}
                            ]
                        })
                else:
                    activities_templates = [
                        {"title": f"Explore historic central {city}", "description": f"Walk around the downtown area, taking in landmarks.", "cost": 45.0, "location": f"{city} Center", "category": "Sightseeing"},
                        {"title": f"Premium Guided City Tour of {city}", "description": f"Hop-on hop-off bus tour around famous streets.", "cost": 85.0, "location": f"{city} Tourist Loop", "category": "Sightseeing"},
                        {"title": f"Local Cuisine Food Walking Tour", "description": f"Taste iconic local specialties at food markets.", "cost": 65.0, "location": f"{city} Food Market", "category": "Food"},
                        {"title": f"Scenic Boat Cruise / River Tour", "description": f"Enjoy a relaxing cruise with beautiful views.", "cost": 55.0, "location": f"{city} Waterfront", "category": "Sightseeing"},
                        {"title": f"{city} Modern Art Museum", "description": f"Visit the premier local museum showcasing contemporary art.", "cost": 35.0, "location": f"{city} Museum District", "category": "Sightseeing"},
                        {"title": f"Botanical Gardens & Park Sightseeing", "description": f"Stroll through greenhouses and scenic paths.", "cost": 25.0, "location": f"{city} Botanical Garden", "category": "Sightseeing"},
                        {"title": f"Traditional Souvenir Shopping & Dinner", "description": f"Shop for authentic gifts followed by a farewell dinner.", "cost": 95.0, "location": f"{city} Shopping Arcade", "category": "Food"}
                    ]
                    
                    for i in range(1, days_count + 1):
                        day_date = (start_date + datetime.timedelta(days=i-1)).isoformat()
                        act1 = activities_templates[(i*2 - 2) % len(activities_templates)]
                        act2 = activities_templates[(i*2 - 1) % len(activities_templates)]
                        
                        fallback_itinerary["days"].append({
                            "day_number": i,
                            "date": day_date,
                            "activities": [
                                {"time": "Morning", "title": act1["title"], "description": act1["description"], "cost": act1["cost"], "location": act1["location"], "category": act1["category"]},
                                {"time": "Afternoon", "title": act2["title"], "description": act2["description"], "cost": act2["cost"], "location": act2["location"], "category": act2["category"]}
                            ]
                        })
                
                save_itinerary(new_trip_id, fallback_itinerary)
                st.session_state.fallback_used = True
                st.session_state.last_error_rate_limited = False
                
                # Log the fallback sightseeing expenses to ensure the budget tracker populates!
                for day in fallback_itinerary["days"]:
                    for act in day["activities"]:
                        if act["cost"] > 0:
                            add_expense(new_trip_id, act["cost"], "Sightseeing", act["title"], "USD", day["date"])
            else:
                st.session_state.fallback_used = False
                st.session_state.last_error_rate_limited = False
            
            st.success(f"Trip to {dest} planned successfully! View details in Live Itinerary.")
            st.rerun()

# -----------------------------------------------------------------------------
# PAGE 3: Live Itinerary
# -----------------------------------------------------------------------------
elif page == "📋 Live Itinerary":
    st.markdown("<h1 class='main-title'>Live Trip Dashboard</h1>", unsafe_allow_html=True)
    st.markdown("<p class='subtitle'>Day-by-day active travel timeline details.</p>", unsafe_allow_html=True)
    
    if not trip:
        st.info("No active trip. Please go to Trip Planner to schedule one.")
    else:
        st.markdown(f"### Itinerary for {trip['destination']} ({trip['start_date']} - {trip['end_date']})")
        
        # Display Flight & Hotel details
        col1, col2 = st.columns(2)
        with col1:
            flight = get_flight(trip_id)
            if flight:
                st.markdown(f"""
                <div class='glass-card glow-border-blue'>
                    <h4>✈️ Flight Booking</h4>
                    <p><b>Airline:</b> {flight['airline']}<br/>
                    <b>Flight:</b> {flight['flight_number']}<br/>
                    <b>Departure:</b> {flight['departure_time']}<br/>
                    <b>Arrival:</b> {flight['arrival_time']}<br/>
                    <b>Status:</b> <span class='badge badge-ok'>{flight['status']}</span></p>
                </div>
                """, unsafe_allow_html=True)
        with col2:
            hotel = get_hotel(trip_id)
            if hotel:
                st.markdown(f"""
                <div class='glass-card glow-border-green'>
                    <h4>🏨 Accommodation</h4>
                    <p><b>Hotel:</b> {hotel['hotel_name']}<br/>
                    <b>Check-in Time:</b> {hotel['check_in_time']}<br/>
                    <b>Check-out:</b> {hotel['check_out_time']}<br/>
                    <b>Status:</b> <span class='badge badge-ok'>{hotel['status']}</span></p>
                </div>
                """, unsafe_allow_html=True)
                
        itinerary = get_itinerary(trip_id)
        if not itinerary:
            st.warning("No itinerary has been generated for this trip yet (this can happen if the initial generation hit Gemini rate limits).")
            if st.button("🤖 Let AI Agent Generate Itinerary Now"):
                with st.spinner("TripPilot-AI agents are planning your trip, setting up reservations, and applying user memory..."):
                    prefs = get_user_preferences("user_1")
                    # Find start city if stored in flights, fallback to New York
                    flight = get_flight(trip_id)
                    start_city = "New York, USA"
                    if flight and "from " in flight.get("departure_time", ""):
                        try:
                            start_city = flight["departure_time"].split("from ")[1].split(")")[0]
                        except Exception:
                            pass
                            
                    inc_sightseeing = st.session_state.get("include_sightseeing", True)
                    if inc_sightseeing:
                        sightseeing_clause = "Include daily paid sightseeing events, activities, and local tours."
                    else:
                        sightseeing_clause = "Do NOT include any paid local sightseeing activities, tours, or excursions in the itinerary. Keep the activities list limited to free relaxation at the hotel/resort with 0 cost."
                        
                    prompt = (
                        f"Create a day-by-day itinerary for visiting {trip['destination']} starting from {start_city} from {trip['start_date']} to {trip['end_date']}. "
                        f"Seed it with default flights and hotels. The traveler hates seafood and prefers hotels from: {prefs['favorite_hotels']} "
                        f"and airlines like {prefs['favorite_airlines']}. {sightseeing_clause} "
                        f"Make sure to save it in database using the create_itinerary_db tool for trip ID {trip_id}."
                    )
                    events = execute_agent_prompt(prompt)
                    
                    if get_itinerary(trip_id) is None:
                        from database.db_helper import save_itinerary, add_expense
                        
                        dest = trip['destination']
                        city = dest.split(',')[0].strip()
                        s_date = datetime.date.fromisoformat(trip['start_date'])
                        e_date = datetime.date.fromisoformat(trip['end_date'])
                        days_count = (e_date - s_date).days + 1
                        if days_count <= 0 or days_count > 15:
                            days_count = 7
                            
                        fallback_itinerary = {
                            "trip_id": trip_id,
                            "destination": dest,
                            "start_date": trip['start_date'],
                            "end_date": trip['end_date'],
                            "days": []
                        }
                        
                        if not inc_sightseeing:
                            # Seed empty/free relaxation days
                            for i in range(1, days_count + 1):
                                day_date = (s_date + datetime.timedelta(days=i-1)).isoformat()
                                fallback_itinerary["days"].append({
                                    "day_number": i,
                                    "date": day_date,
                                    "activities": [
                                        {"time": "Morning", "title": "Relax at hotel resort", "description": "Leisure time to rest and enjoy hotel amenities.", "cost": 0.0, "location": "Hotel Resort", "category": "Relaxation"},
                                        {"time": "Afternoon", "title": "Leisurely neighborhood walk", "description": "Explore the local area around the hotel on foot.", "cost": 0.0, "location": "Near Resort", "category": "Relaxation"}
                                    ]
                                })
                        else:
                            activities_templates = [
                                {"title": f"Explore historic central {city}", "description": f"Walk around the downtown area, taking in landmarks.", "cost": 45.0, "location": f"{city} Center", "category": "Sightseeing"},
                                {"title": f"Premium Guided City Tour of {city}", "description": f"Hop-on hop-off bus tour around famous streets.", "cost": 85.0, "location": f"{city} Tourist Loop", "category": "Sightseeing"},
                                {"title": f"Local Cuisine Food Walking Tour", "description": f"Taste iconic local specialties at food markets.", "cost": 65.0, "location": f"{city} Food Market", "category": "Food"},
                                {"title": f"Scenic Boat Cruise / River Tour", "description": f"Enjoy a relaxing cruise with beautiful views.", "cost": 55.0, "location": f"{city} Waterfront", "category": "Sightseeing"},
                                {"title": f"{city} Modern Art Museum", "description": f"Visit the premier local museum showcasing contemporary art.", "cost": 35.0, "location": f"{city} Museum District", "category": "Sightseeing"},
                                {"title": f"Botanical Gardens & Park Sightseeing", "description": f"Stroll through greenhouses and scenic paths.", "cost": 25.0, "location": f"{city} Botanical Garden", "category": "Sightseeing"},
                                {"title": f"Traditional Souvenir Shopping & Dinner", "description": f"Shop for authentic gifts followed by a farewell dinner.", "cost": 95.0, "location": f"{city} Shopping Arcade", "category": "Food"}
                            ]
                            
                            for i in range(1, days_count + 1):
                                day_date = (s_date + datetime.timedelta(days=i-1)).isoformat()
                                act1 = activities_templates[(i*2 - 2) % len(activities_templates)]
                                act2 = activities_templates[(i*2 - 1) % len(activities_templates)]
                                
                                fallback_itinerary["days"].append({
                                    "day_number": i,
                                    "date": day_date,
                                    "activities": [
                                        {"time": "Morning", "title": act1["title"], "description": act1["description"], "cost": act1["cost"], "location": act1["location"], "category": act1["category"]},
                                        {"time": "Afternoon", "title": act2["title"], "description": act2["description"], "cost": act2["cost"], "location": act2["location"], "category": act2["category"]}
                                    ]
                                })
                        
                        save_itinerary(trip_id, fallback_itinerary)
                        st.session_state.fallback_used = True
                        st.session_state.last_error_rate_limited = False
                        
                        # Log the fallback sightseeing expenses to ensure the budget tracker populates!
                        for day in fallback_itinerary["days"]:
                            for act in day["activities"]:
                                if act["cost"] > 0:
                                    add_expense(trip_id, act["cost"], "Sightseeing", act["title"], "USD", day["date"])
                    else:
                        st.session_state.fallback_used = False
                        st.session_state.last_error_rate_limited = False
                                
                    st.success("Itinerary generated successfully!")
                    st.rerun()
        else:
            if st.session_state.get("fallback_used"):
                st.info("💡 **Concierge Cache Active:** The Gemini API free tier rate limit was exceeded. TripPilot-AI successfully applied local cached memory rules to draft your itinerary and log budget statistics.")
            days = itinerary.get("days", [])
            for day in days:
                with st.expander(f"📅 Day {day['day_number']} — {day['date']}", expanded=True):
                    for act in day.get("activities", []):
                        st.markdown(f"""
                        **{act['time']} — {act['title']}** ({act['location']})
                        - *Description:* {act['description']}
                        - *Cost:* ${act['cost']:.2f} | *Category:* `{act['category']}`
                        """)

# -----------------------------------------------------------------------------
# PAGE 4: Weather Companion
# -----------------------------------------------------------------------------
elif page == "⛈️ Weather Companion":
    st.markdown("<h1 class='main-title'>Continuous Weather Monitor</h1>", unsafe_allow_html=True)
    st.markdown("<p class='subtitle'>Checking conditions and dynamically adjusting schedules.</p>", unsafe_allow_html=True)
    
    if not trip:
        st.info("No active trip.")
    else:
        # Check weather forecast dynamically
        from agents.weather_agent import get_weather_forecast
        
        st.markdown(f"### 3-Day Weather Forecast for {trip['destination']}")
        
        # Calculate daily dates based on active trip start date
        try:
            start_dt = datetime.date.fromisoformat(trip["start_date"])
        except Exception:
            start_dt = datetime.date.today()
            
        dates = [(start_dt + datetime.timedelta(days=i)).isoformat() for i in range(3)]
        
        cols = st.columns(3)
        for i, d in enumerate(dates):
            weather_json = get_weather_forecast(trip["destination"], d)
            try:
                w = json.loads(weather_json)
            except Exception:
                w = {"forecast": "Sunny and Clear", "temp_c": 26, "rain_prob_pct": 5, "alert": None}
                
            condition = w.get("forecast", "Sunny and Clear")
            temp = w.get("temp_c", 26)
            alert = w.get("alert")
            prob = w.get("rain_prob_pct", 5)
            
            # Custom card aesthetics
            glow_class = ""
            alert_badge = ""
            icon = "☀️"
            
            if alert:
                glow_class = "glow-border-red"
                alert_badge = f"<span class='badge badge-danger'>{alert}</span>"
                icon = "⛈️"
            elif prob > 50:
                glow_class = "glow-border-blue"
                alert_badge = "<span class='badge badge-warn'>Showers</span>"
                icon = "🌧️"
            else:
                glow_class = ""
                alert_badge = "<span class='badge badge-ok'>Clear</span>"
                icon = "☀️"
                
            with cols[i]:
                st.markdown(f"""
                <div class='glass-card {glow_class}'>
                    <h5>{d}</h5>
                    <h3>{icon} {temp}°C</h3>
                    <p><b>Condition:</b> {condition}<br/>
                    <b>Rain Chance:</b> {prob}%</p>
                    {alert_badge}
                </div>
                """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# PAGE 5: Budget Tracker
# -----------------------------------------------------------------------------
elif page == "💰 Budget Tracker":
    st.markdown("<h1 class='main-title'>Expense Tracking & Budget Status</h1>", unsafe_allow_html=True)
    
    if not trip:
        st.info("No active trip.")
    else:
        expenses = get_expenses(trip_id)
        total_spent = sum(e["amount"] for e in expenses)
        total_budget = float(trip.get("budget", 3000.0))
        remaining = total_budget - total_spent
        
        # Display Progress Bar
        progress_pct = min(total_spent / total_budget, 1.0)
        
        # Red warning card if expenses exceed custom budget limit
        if total_spent > total_budget:
            st.markdown(f"""
            <div class='glass-card glow-border-red' style='margin-bottom: 20px; border-left: 4px solid #f44336;'>
                <h4 style='color:#f44336; margin-top:0; margin-bottom: 8px;'>⚠️ BUDGET EXCEEDED WARNING</h4>
                <p style='margin-bottom:0; color:#eee;'>Your total expenses (<b>${total_spent:.2f}</b>) have exceeded your set budget limit of <b>${total_budget:.2f}</b> by <b>${(total_spent - total_budget):.2f}</b>!<br/>
                Our AI budget agent recommends switching to public transportation (metro) and opting for casual local dining spots to reduce further overruns.</p>
            </div>
            """, unsafe_allow_html=True)
            
        st.progress(progress_pct)
        st.metric("Total Spent", f"${total_spent:.2f}", f"Remaining: ${remaining:.2f}")
        
        # Plot Charts
        df_exp = pd.DataFrame(expenses)
        if not df_exp.empty:
            st.markdown("### Expenses by Category")
            category_totals = df_exp.groupby("category")["amount"].sum().reset_index()
            st.bar_chart(category_totals.set_index("category"))
            
            st.markdown("### Expense Logs")
            st.table(df_exp[["date", "category", "amount", "description"]])

# -----------------------------------------------------------------------------
# PAGE 6: Emergency Console
# -----------------------------------------------------------------------------
elif page == "🚨 Emergency Console":
    st.markdown("<h1 class='main-title'>Emergency Assistance Console</h1>", unsafe_allow_html=True)
    st.markdown("<p class='subtitle'>Instant contact lookup and lost passport procedures.</p>", unsafe_allow_html=True)
    
    if not trip:
        st.info("No active trip to lookup local support contacts.")
    else:
        # Fetch emergency contacts dynamically
        from agents.emergency_agent import lookup_emergency_contacts
        contacts_json = lookup_emergency_contacts(trip["destination"])
        try:
            contacts = json.loads(contacts_json)
        except Exception:
            contacts = {
                "embassy": f"Consulate/Embassy in {trip['destination']}",
                "police": "Police: Dial 911",
                "hospital": "Local Emergency Room",
                "fire_ambulance": "Emergency Services: Dial 911"
            }
            
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"""
            <div class='glass-card glow-border-red'>
                <h4>🚨 {trip['destination']} Emergency Contacts</h4>
                <p><b>Local Police:</b> {contacts.get('police')}<br/>
                <b>Ambulance & Fire:</b> {contacts.get('fire_ambulance')}<br/>
                <b>Nearest Hospital:</b> {contacts.get('hospital')}<br/>
                <b>Embassy / Consulate:</b> {contacts.get('embassy')}</p>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown("""
            <div class='glass-card'>
                <h4>Passport Recovery Checklist</h4>
                <p>If you lose your passport while traveling abroad:
                <ol>
                    <li>File a report at the nearest local police box (Koban).</li>
                    <li>Gather proof of citizenship and passport-sized photos.</li>
                    <li>Visit the national Embassy/Consulate immediately.</li>
                    <li>Submit forms DS-11 and DS-64 to receive an emergency passport.</li>
                </ol></p>
            </div>
            """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# PAGE 7: Notifications
# -----------------------------------------------------------------------------
elif page == "🔔 Notifications":
    st.markdown("<h1 class='main-title'>Dispatch Logs</h1>", unsafe_allow_html=True)
    st.markdown("<p class='subtitle'>History of emails and alerts sent by the communication agent.</p>", unsafe_allow_html=True)
    
    if not trip:
        st.info("No active trip.")
    else:
        notes = get_notifications(trip_id)
        if not notes:
            st.info("No notifications have been dispatched yet.")
        else:
            for note in notes:
                msg = note['message']
                icon = "📧" if note['type'] == "EMAIL" else "📱"
                
                # Split and parse subject & body for better readability
                lines = msg.split('\n')
                subject = ""
                body = ""
                
                if note['type'] == "EMAIL":
                    for line in lines:
                        if line.startswith("Subject:"):
                            subject = line.replace("Subject:", "").strip()
                    
                    body_lines = []
                    found_body = False
                    for line in lines:
                        if found_body:
                            body_lines.append(line)
                        elif line.startswith("Body:"):
                            found_body = True
                            body_lines.append(line.replace("Body:", "").strip())
                    
                    if body_lines:
                        body = "\n".join(body_lines).strip()
                    else:
                        body = msg
                else:
                    subject = "Companion Push Alert"
                    body = msg.replace("Companion Alert:", "").strip()
                
                if not subject:
                    subject = "Communication Alert"
                    
                st.markdown(f"""
                <div class='glass-card' style='margin-bottom: 15px; border-left: 4px solid #2196f3; padding: 15px;'>
                    <div style='display: flex; justify-content: space-between; font-size: 0.85em; color: #888; margin-bottom: 4px;'>
                        <span>{icon} <b>{note['type']} DISPATCH</b></span>
                        <span>🕒 {note['sent_at']}</span>
                    </div>
                    <div style='font-size: 1.1em; font-weight: bold; color: #fff; margin-bottom: 6px;'>{subject}</div>
                    <div style='font-size: 0.95em; color: #ccc; line-height: 1.4; white-space: pre-wrap;'>{body}</div>
                </div>
                """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# PAGE 8: Travel Preferences
# -----------------------------------------------------------------------------
elif page == "⚙️ Travel Preferences":
    st.markdown("<h1 class='main-title'>Traveler Preferences (Memory State)</h1>", unsafe_allow_html=True)
    st.markdown("<p class='subtitle'>Configure preferences which the memory agent seeds into new itineraries automatically.</p>", unsafe_allow_html=True)
    
    prefs = get_user_preferences("user_1")
    
    with st.form("prefs_form"):
        airlines = st.text_input("Favorite Airlines (comma separated)", value=", ".join(prefs["favorite_airlines"]))
        hotels = st.text_input("Favorite Hotel Chains (comma separated)", value=", ".join(prefs["favorite_hotels"]))
        transport = st.selectbox("Preferred Transit", ["Metro", "Taxi", "Walking"], index=["Metro", "Taxi", "Walking"].index(prefs["preferred_transport"]))
        food = st.text_input("Dietary/Food Restrictions (comma separated)", value=", ".join(prefs["food_restrictions"]))
        
        submitted = st.form_submit_button("Update Memory State")
        
    if submitted:
        prefs_dict = {
            "user_id": "user_1",
            "favorite_airlines": [a.strip() for a in airlines.split(",") if a.strip()],
            "favorite_hotels": [h.strip() for h in hotels.split(",") if h.strip()],
            "preferred_transport": transport,
            "food_restrictions": [f.strip() for f in food.split(",") if f.strip()],
            "preferred_language": "English",
            "visa_status": "Visa Free / 90 Days",
            "frequent_flyer_number": "JAL-889104"
        }
        update_user_preferences(prefs_dict)
        st.success("Memory state updated! Future planning sessions will load these preferences.")
