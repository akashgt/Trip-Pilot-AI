import sqlite3
import os
import json
import datetime
from typing import Optional, List, Dict, Any

# Ensure database directory exists
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "trip.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database tables."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Trips
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            destination TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            status TEXT NOT NULL,
            budget REAL DEFAULT 3000.0
        )
    """)
    try:
        cursor.execute("ALTER TABLE trips ADD COLUMN budget REAL DEFAULT 3000.0")
    except sqlite3.OperationalError:
        pass
    
    # 2. Itineraries
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS itineraries (
            trip_id INTEGER PRIMARY KEY,
            itinerary_json TEXT NOT NULL,
            FOREIGN KEY (trip_id) REFERENCES trips (id) ON DELETE CASCADE
        )
    """)
    
    # 3. Flights
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS flights (
            trip_id INTEGER PRIMARY KEY,
            flight_number TEXT NOT NULL,
            departure_time TEXT NOT NULL,
            arrival_time TEXT NOT NULL,
            status TEXT NOT NULL,
            delay_minutes INTEGER DEFAULT 0,
            airline TEXT NOT NULL,
            FOREIGN KEY (trip_id) REFERENCES trips (id) ON DELETE CASCADE
        )
    """)
    
    # 4. Hotels
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hotels (
            trip_id INTEGER PRIMARY KEY,
            hotel_name TEXT NOT NULL,
            check_in_time TEXT NOT NULL,
            check_out_time TEXT NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (trip_id) REFERENCES trips (id) ON DELETE CASCADE
        )
    """)
    
    # 5. Expenses
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            currency TEXT DEFAULT 'USD',
            date TEXT NOT NULL,
            FOREIGN KEY (trip_id) REFERENCES trips (id) ON DELETE CASCADE
        )
    """)
    
    # 6. User Preferences
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id TEXT PRIMARY KEY,
            favorite_airlines TEXT, -- JSON list
            favorite_hotels TEXT,   -- JSON list
            preferred_language TEXT DEFAULT 'English',
            preferred_transport TEXT DEFAULT 'Metro',
            food_restrictions TEXT, -- JSON list
            visa_status TEXT DEFAULT 'Not Required',
            frequent_flyer_number TEXT
        )
    """)
    
    # 7. Notifications
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER,
            message TEXT NOT NULL,
            type TEXT NOT NULL, -- e.g., 'EMAIL', 'PUSH', 'ALERT'
            sent_at TEXT NOT NULL
        )
    """)
    
    # 8. Audit Logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            severity TEXT NOT NULL,
            event TEXT NOT NULL,
            details TEXT NOT NULL
        )
    """)
    
    # Seed default user preferences
    cursor.execute("SELECT COUNT(*) FROM user_preferences WHERE user_id = 'user_1'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO user_preferences (
                user_id, favorite_airlines, favorite_hotels, preferred_language, 
                preferred_transport, food_restrictions, visa_status, frequent_flyer_number
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'user_1',
            json.dumps(["ANA", "JAL", "United"]),
            json.dumps(["Hilton", "Hyatt", "Park Hyatt"]),
            "English",
            "Metro",
            json.dumps(["No Seafood"]),
            "Visa Free / 90 Days",
            "JAL-889104"
        ))
        
    conn.commit()
    conn.close()

# Initialize DB on import
init_db()

# --- DB Access / Helper Methods ---

def log_audit(severity: str, event: str, details: dict):
    """Inserts a structured security or system audit log."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.datetime.utcnow().isoformat() + "Z"
    cursor.execute(
        "INSERT INTO audit_logs (timestamp, severity, event, details) VALUES (?, ?, ?, ?)",
        (now, severity, event, json.dumps(details))
    )
    conn.commit()
    conn.close()

def get_audit_logs() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 100")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_user_preferences(user_id: str) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_preferences WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        res = dict(row)
        res['favorite_airlines'] = json.loads(res['favorite_airlines'] or "[]")
        res['favorite_hotels'] = json.loads(res['favorite_hotels'] or "[]")
        res['food_restrictions'] = json.loads(res['food_restrictions'] or "[]")
        return res
    return {
        "user_id": user_id,
        "favorite_airlines": [],
        "favorite_hotels": [],
        "preferred_language": "English",
        "preferred_transport": "Metro",
        "food_restrictions": [],
        "visa_status": "Not Required",
        "frequent_flyer_number": None
    }

def update_user_preferences(prefs: dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO user_preferences (
            user_id, favorite_airlines, favorite_hotels, preferred_language,
            preferred_transport, food_restrictions, visa_status, frequent_flyer_number
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        prefs["user_id"],
        json.dumps(prefs.get("favorite_airlines", [])),
        json.dumps(prefs.get("favorite_hotels", [])),
        prefs.get("preferred_language", "English"),
        prefs.get("preferred_transport", "Metro"),
        json.dumps(prefs.get("food_restrictions", [])),
        prefs.get("visa_status", "Not Required"),
        prefs.get("frequent_flyer_number")
    ))
    conn.commit()
    conn.close()

def create_trip(user_id: str, destination: str, start_date: str, end_date: str, budget: float = 3000.0) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO trips (user_id, destination, start_date, end_date, status, budget) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, destination, start_date, end_date, 'PLANNED', budget)
    )
    trip_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return trip_id

def get_active_trip(user_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trips WHERE user_id = ? AND status != 'COMPLETED' ORDER BY id DESC LIMIT 1", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def save_itinerary(trip_id: int, itinerary_data: dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO itineraries (trip_id, itinerary_json) VALUES (?, ?)",
        (trip_id, json.dumps(itinerary_data))
    )
    conn.commit()
    conn.close()

def get_itinerary(trip_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT itinerary_json FROM itineraries WHERE trip_id = ?", (trip_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return json.loads(row['itinerary_json'])
    return None

def save_flight(trip_id: int, flight: dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO flights (
            trip_id, flight_number, departure_time, arrival_time, status, delay_minutes, airline
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        trip_id,
        flight["flight_number"],
        flight["departure_time"],
        flight["arrival_time"],
        flight.get("status", "ON_TIME"),
        flight.get("delay_minutes", 0),
        flight["airline"]
    ))
    conn.commit()
    conn.close()

def get_flight(trip_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM flights WHERE trip_id = ?", (trip_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def save_hotel(trip_id: int, hotel: dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO hotels (
            trip_id, hotel_name, check_in_time, check_out_time, status
        ) VALUES (?, ?, ?, ?, ?)
    """, (
        trip_id,
        hotel["hotel_name"],
        hotel["check_in_time"],
        hotel["check_out_time"],
        hotel.get("status", "CONFIRMED")
    ))
    conn.commit()
    conn.close()

def get_hotel(trip_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hotels WHERE trip_id = ?", (trip_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def add_expense(trip_id: int, amount: float, category: str, description: str, currency: str, date: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO expenses (trip_id, amount, category, description, currency, date)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (trip_id, amount, category, description, currency, date))
    conn.commit()
    conn.close()

def get_expenses(trip_id: int) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM expenses WHERE trip_id = ? ORDER BY date DESC", (trip_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def log_notification(trip_id: int, message: str, notification_type: str = 'EMAIL'):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO notifications (trip_id, message, type, sent_at) VALUES (?, ?, ?, ?)",
        (trip_id, message, notification_type, now)
    )
    conn.commit()
    conn.close()

def get_notifications(trip_id: int) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM notifications WHERE trip_id = ? ORDER BY id DESC", (trip_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]
