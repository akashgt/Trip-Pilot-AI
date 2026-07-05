# Kaggle AI Agents Capstone: TripPilot-AI Submission Writeup

**Project Title:** TripPilot-AI: Proactive Travel Concierge  
**Track:** Concierge Agents Track  
**Core Technologies:** Google ADK 2.0, Streamlit, SQLite, FastMCP, Uvicorn, Docker Compose

---

## 🎯 Executive Summary
TripPilot-AI is an agentic, event-driven travel companion designed to monitor an active trip and autonomously coordinate 9 specialized agents. Unlike ordinary travel chatbots, it intercepts disruptions (flight delays, storm warnings, budget issues) and acts preemptively—re-calculating schedules, proposing hotel check-in adjustments, swapping outdoor activities for indoor alternatives, and alert-dispatching—with built-in Human-in-the-loop (HITL) safeguards.

---

## 🏗️ Architectural Framework

TripPilot-AI follows a modular architecture:
1. **Security Gateway:** Intercepts all traffic. Scrubs PII and checks for prompt injection.
2. **Orchestrator (Google ADK 2.0 Graph):** Dynamically delegates tasks using sub-agents registered as tools.
3. **Database Layer (SQLite):** Maintains relational schemas for trips, itineraries, flights, hotels, expenses, and notifications.
4. **Simulator Cockpit (Streamlit):** Serves as the operator control board, allowing direct injection of flight delays and storm events.

---

## 🤖 The 9 Specialized Agents

Each agent is built using Google ADK `LlmAgent` and registered in the orchestrator:

1. **Memory Agent (`memory_agent.py`):**
   - Feeds historical preferences (favorite airlines/hotels/dietary restrictions) into the planner.
2. **Planner Agent (`planner_agent.py`):**
   - Handles itinerary CRUD operations, optimized with local attractions and constraints.
3. **Flight Agent (`flight_agent.py`):**
   - Adjusts schedules and departures when flight delay alerts trigger.
4. **Hotel Agent (`hotel_agent.py`):**
   - Shifts hotel check-in windows during travel delays.
5. **Weather Agent (`weather_agent.py`):**
   - Monitors warnings and fetches indoor museum/gallery options.
6. **Transport Agent (`transport_agent.py`):**
   - Suggests transit passes, walking directions, or cab fares.
7. **Budget Agent (`budget_agent.py`):**
   - Calculates real-time total expenses and triggers warnings.
8. **Notification Agent (`notification_agent.py`):**
   - Formats and sends email alerts and push messages to companions.
9. **Emergency Agent (`emergency_agent.py`):**
   - Fetches embassy addresses, local police dials, and lost passport checklist steps.

---

## 🔒 Security Gate & Mitigation Strategy
Our two-tier security filter intercepts prompt injections (using keyword overrides) and redacts PII using strict regex checks:
- **PII Scrubbing:** Credit cards, passport patterns, emails, and phone numbers are logged as `[REDACTED]` and stored in security audits.
- **Injection Shield:** Flags jailbreaks like "ignore previous instructions", and diverts execution immediately to a blocked message terminal node.

---

## 🧪 Verification & Robustness
The automated test suite in `tests/unit/test_travel_concierge.py` tests:
1. **SQLite CRUD Operations:** Verify initial seeding, itinerary storage, and expense calculation.
2. **PII Redaction Filters:** Confirms credit card and passport string replacement.
3. **Prompt Injection Blocks:** Tests blocking of bypass/jailbreak attempts.
All unit tests execute successfully in under 21 seconds.
