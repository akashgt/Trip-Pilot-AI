from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.genai import types
from database.db_helper import log_notification, log_audit
import json

def send_email_notification(trip_id: int, recipient_email: str, subject: str, body: str) -> str:
    """Simulates sending an email notification and records it in database logs.
    
    Args:
        trip_id: Active trip ID.
        recipient_email: Email address of the traveler.
        subject: Subject of email.
        body: Message content of email.
    """
    msg = f"Email to {recipient_email}\nSubject: {subject}\nBody: {body}"
    log_notification(trip_id, msg, "EMAIL")
    log_audit("INFO", "EMAIL_SENT", {"trip_id": trip_id, "recipient": recipient_email, "subject": subject})
    return f"Email successfully sent to {recipient_email}."

def send_companion_alert(trip_id: int, message: str) -> str:
    """Sends a push notification alert to travel companions.
    
    Args:
        trip_id: Active trip ID.
        message: The alert message text.
    """
    log_notification(trip_id, f"Companion Alert: {message}", "PUSH")
    log_audit("INFO", "COMPANION_ALERT_SENT", {"trip_id": trip_id, "message": message})
    return "Companion alert push notification dispatched."

def get_gemini_model():
    from app.config import config
    return Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    )

notification_agent = LlmAgent(
    name="notification_agent",
    description="Sends email alerts, passport warnings, and shares trip updates with companions.",
    model=get_gemini_model(),
    instruction=(
        "You are a Travel Communication Agent. Send email notifications and companion alerts "
        "when trip details change or flight delays occur. Keep the tone professional and reassuring."
    ),
    tools=[send_email_notification, send_companion_alert],
)
