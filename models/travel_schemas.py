from pydantic import BaseModel, Field
from typing import List, Optional

class UserPreferences(BaseModel):
    user_id: str = Field(..., description="Unique ID of the traveler.")
    favorite_airlines: List[str] = Field(default_factory=list, description="Preferred airlines (e.g. ['ANA', 'JAL']).")
    favorite_hotels: List[str] = Field(default_factory=list, description="Preferred hotels or chains (e.g. ['Hilton', 'Hyatt']).")
    preferred_language: str = Field(default="English", description="Traveler's language of choice.")
    preferred_transport: str = Field(default="Metro", description="Default local transport: Metro, Taxi, walking, etc.")
    food_restrictions: List[str] = Field(default_factory=list, description="Dietary limits or allergies.")
    visa_status: str = Field(default="Not Required", description="Visa requirement status for destination.")
    frequent_flyer_number: Optional[str] = Field(None, description="Frequent flyer number for bookings.")

class FlightDetails(BaseModel):
    flight_number: str = Field(..., description="Flight number (e.g. NH206).")
    departure_time: str = Field(..., description="Departure date/time in ISO or human readable format.")
    arrival_time: str = Field(..., description="Estimated arrival time.")
    status: str = Field(default="ON_TIME", description="Flight status: ON_TIME, DELAYED, CANCELLED.")
    delay_minutes: int = Field(default=0, description="Amount of delay in minutes.")
    airline: str = Field(..., description="Airline name.")

class HotelReservation(BaseModel):
    hotel_name: str = Field(..., description="Name of the hotel.")
    check_in_time: str = Field(..., description="Rescheduled or scheduled check-in time.")
    check_out_time: str = Field(..., description="Check-out time.")
    status: str = Field(default="CONFIRMED", description="Reservation status.")

class Activity(BaseModel):
    time: str = Field(..., description="Time of the activity (e.g. 10:00 AM).")
    title: str = Field(..., description="Name of the activity or sight.")
    description: str = Field(..., description="Quick summary of what to do.")
    cost: float = Field(default=0.0, description="Cost in local currency.")
    category: str = Field(default="sightseeing", description="Category: sightseeing, dining, transit, hotel.")
    location: str = Field(..., description="Location name or address.")

class ItineraryDay(BaseModel):
    day_number: int = Field(..., description="Day number of the trip (1-indexed).")
    date: str = Field(..., description="Date (YYYY-MM-DD).")
    activities: List[Activity] = Field(default_factory=list, description="List of activities for this day.")

class TripItinerary(BaseModel):
    trip_id: int = Field(..., description="SQLite ID of the trip.")
    destination: str = Field(..., description="Destination city/country.")
    start_date: str = Field(..., description="Trip start date.")
    end_date: str = Field(..., description="Trip end date.")
    days: List[ItineraryDay] = Field(default_factory=list, description="List of itinerary days.")

class ExpenseItem(BaseModel):
    trip_id: int
    amount: float
    category: str = Field(..., description="Category: Flight, Hotel, Food, Transport, Activities, Miscellaneous")
    description: str
    currency: str = Field(default="USD")
    date: str

class ItineraryOutput(BaseModel):
    trip_summary: str = Field(..., description="A high level text summary of the trip itinerary.")
    days: List[ItineraryDay] = Field(..., description="List of planned activities day-by-day.")
