from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.genai import types
from database.db_helper import get_expenses, add_expense, log_audit
import json

def get_trip_expenses(trip_id: int) -> str:
    """Fetches all expenses logged for a trip.
    
    Args:
        trip_id: Active trip ID.
    """
    expenses = get_expenses(trip_id)
    return json.dumps(expenses, indent=2)

def log_expense(trip_id: int, amount: float, category: str, description: str, date: str) -> str:
    """Logs a travel expense in the database.
    
    Args:
        trip_id: Active trip ID.
        amount: Expense amount in USD.
        category: Expense category (Flight, Hotel, Food, Transport, Sightseeing, Miscellaneous).
        description: Description of what was purchased.
        date: Date of expense (YYYY-MM-DD).
    """
    add_expense(trip_id, amount, category, description, 'USD', date)
    log_audit("INFO", "EXPENSE_LOGGED", {
        "trip_id": trip_id,
        "amount": amount,
        "category": category,
        "description": description
    })
    return f"Successfully logged expense of ${amount:.2f} under category '{category}'."

def check_budget_status(trip_id: int, total_budget: float) -> str:
    """Checks the overall budget status. Compares total spent vs total budget limit.
    
    Args:
        trip_id: Active trip ID.
        total_budget: Total allowed budget limit in USD.
    """
    expenses = get_expenses(trip_id)
    total_spent = sum(item["amount"] for item in expenses)
    remaining = total_budget - total_spent
    status = "OK"
    warnings = []
    
    if total_spent > total_budget:
        status = "EXCEEDED"
        warnings.append(f"Budget exceeded by ${abs(remaining):.2f}!")
        log_audit("WARNING", "BUDGET_EXCEEDED", {"trip_id": trip_id, "spent": total_spent, "budget": total_budget})
    elif total_spent >= total_budget * 0.9:
        status = "WARNING"
        warnings.append("Budget is 90% spent. Exercise caution on future spending.")
        log_audit("INFO", "BUDGET_WARNING_90_PERCENT", {"trip_id": trip_id, "spent": total_spent, "budget": total_budget})

    result = {
        "total_budget": total_budget,
        "total_spent": total_spent,
        "remaining": remaining,
        "status": status,
        "warnings": warnings
    }
    return json.dumps(result, indent=2)

def get_cheaper_alternatives(category: str) -> str:
    """Suggests cheaper alternatives for specific expense categories (e.g. Dining, Transport).
    
    Args:
        category: Expense category to find cheaper options for.
    """
    cat = category.lower()
    if "food" in cat or "dining" in cat or "restaurant" in cat:
        alts = [
            {"name": "Local Ramen Shops (Ichiran/Ippudo)", "avg_price": "$10-$15 per meal", "type": "Casual Dining"},
            {"name": "Convenience Stores (7-Eleven / FamilyMart bento)", "avg_price": "$4-$7 per meal", "type": "Quick Grab"},
            {"name": "CoCo Ichibanya Curry", "avg_price": "$8-$12 per meal", "type": "Casual Dining"}
        ]
    elif "transport" in cat or "taxi" in cat:
        alts = [
            {"name": "Tokyo Subway 72-Hour Pass", "avg_price": "$10 total ($3.33/day)", "type": "Subway Pass"},
            {"name": "Suica / Pasmo Rechargeable IC Card", "avg_price": "Pay per ride (typically $1.50 - $3.00)", "type": "Smart Transit Card"},
            {"name": "Walking (Highly walkable neighborhoods)", "avg_price": "$0.00", "type": "Walking"}
        ]
    else:
        alts = [
            {"name": "Use free walking tours", "avg_price": "Free", "type": "Activities"},
            {"name": "Visit public parks & shrines (e.g. Meiji Jingu, Senso-ji)", "avg_price": "Free entry", "type": "Sightseeing"}
        ]
    return json.dumps(alts, indent=2)

def get_gemini_model():
    from app.config import config
    return Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    )

budget_agent = LlmAgent(
    name="budget_agent",
    description="Logs expenses, monitors budget limits, and suggests cheaper alternatives.",
    model=get_gemini_model(),
    instruction=(
        "You are a Budget Specialist Agent. Your role is to record traveler expenses, check total spending limits, "
        "warn the traveler if they exceed budgets, and recommend cheaper alternatives for food, transit, or activities."
    ),
    tools=[get_trip_expenses, log_expense, check_budget_status, get_cheaper_alternatives],
)
