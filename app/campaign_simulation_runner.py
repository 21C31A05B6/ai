"""
Simulation runner — runs a full AI conversation for a contact without Twilio.
Uses Groq to generate realistic caller questions, then answers them with Groq.
Stores every turn in PostgreSQL exactly like a real call.
"""

import time
from typing import Optional

from app.database import (
    get_campaign_contact_by_id,
    create_call_session_for_contact,
    set_call_contact_map,
    mark_contact_status,
    log_turn,
    update_call_status,
)
from app.ai_logic import get_answer, wants_human, _get_groq_client, GROQ_MODEL
from app.faq_data import GREETING, FAREWELL


# ---------------------------------------------------------------------------
# Generate realistic caller questions using Groq
# ---------------------------------------------------------------------------

_DEFAULT_QUESTIONS = [
    "Hello, I received a call about a job opportunity.",
    "Can you tell me about the interview process?",
    "What documents do I need to prepare?",
    "What is the salary range for the position?",
    "Thank you for the information. Goodbye.",
]


def _generate_caller_questions(contact_name: str, business_type: str = "company") -> list[str]:
    """Use Groq to generate 3-5 realistic questions a candidate might ask on a call."""
    client = _get_groq_client()
    if client is None:
        return _DEFAULT_QUESTIONS

    try:
        prompt = (
            f"You are simulating a phone call where '{contact_name or 'a candidate'}' "
            "has just answered an outbound call from a company's hiring line. "
            "Generate exactly 4 short, realistic things this person would say during the call "
            "(greeting, 2 questions about the job/interview, and a goodbye). "
            "Return ONLY a numbered list, one item per line. "
            "Example:\n1. Hello, who is this?\n2. What is the interview process?\n"
            "3. What salary can I expect?\n4. Thank you, goodbye."
        )
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=200,
        )
        raw = resp.choices[0].message.content.strip()
        lines = []
        for line in raw.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Strip leading "1. " "2. " etc.
            if line[0].isdigit() and len(line) > 2 and line[1] in ".):":
                line = line[2:].strip()
            if line:
                lines.append(line)
        return lines if lines else _DEFAULT_QUESTIONS
    except Exception as e:
        print(f"[SIM] Could not generate questions via Groq: {e}")
        return _DEFAULT_QUESTIONS


# ---------------------------------------------------------------------------
# Main simulation entry point
# ---------------------------------------------------------------------------

def run_conversation_simulation(
    *,
    campaign_id: int,
    campaign_contact_id: int,
    business_type: str = "company",
    scripted_user_utterances: Optional[list[str]] = None,
) -> str:
    """
    Simulate a full AI phone conversation for one contact.

    - Creates a call session in PostgreSQL
    - Uses Groq to generate caller utterances (or uses provided ones)
    - Gets AI answers for each utterance
    - Logs every Q&A turn to call_logs
    - Returns the generated call_sid
    """
    contact = get_campaign_contact_by_id(campaign_id, campaign_contact_id)
    if not contact:
        raise ValueError(f"Contact {campaign_contact_id} not found in campaign {campaign_id}")

    contact_name, contact_phone = contact

    # Create a unique call session
    call_sid = create_call_session_for_contact(
        campaign_id=campaign_id,
        campaign_contact_id=campaign_contact_id,
        contact_name=contact_name,
        contact_phone=contact_phone,
        business_type=business_type,
        status="active",
    )

    # Map call -> contact so admin dashboard can look up name/phone
    set_call_contact_map(
        call_sid=call_sid,
        campaign_id=campaign_id,
        campaign_contact_id=campaign_contact_id,
        contact_name=contact_name,
        contact_phone=contact_phone,
    )

    # Log the AI greeting as the opening turn
    log_turn(call_sid, contact_phone, business_type, "CALL STARTED", GREETING, transferred=False)
    update_call_status(call_sid, contact_phone, business_type, "active")

    # Use provided utterances or generate via Groq
    if scripted_user_utterances:
        utterances = scripted_user_utterances
    else:
        utterances = _generate_caller_questions(contact_name, business_type)

    # Run the conversation
    history = []
    transferred = False

    for user_text in utterances:
        if wants_human(user_text):
            answer = "Certainly. Please hold while I transfer your call."
            log_turn(call_sid, contact_phone, business_type, user_text, answer, transferred=True)
            update_call_status(call_sid, contact_phone, business_type, "transferred")
            transferred = True
            break

        answer, _ = get_answer(business_type, user_text, history=history)
        log_turn(call_sid, contact_phone, business_type, user_text, answer, transferred=False)

        # Build history for multi-turn Groq context
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": answer})

        time.sleep(0.1)  # small delay to avoid rate limits

    # End the call
    log_turn(call_sid, contact_phone, business_type, "[CALL ENDED]", FAREWELL, transferred=transferred)
    update_call_status(call_sid, contact_phone, business_type, "ended")
    mark_contact_status(campaign_id, campaign_contact_id, "called")

    return call_sid
