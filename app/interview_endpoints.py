import os
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.outbound_logic import create_outbound_call

router = APIRouter(prefix="/interview-call", tags=["interview-call"])


class StartPayload(BaseModel):
    caller_number: str  # candidate phone number


@router.post("/start")
async def interview_call_start(payload: StartPayload):
    """Start a real Twilio outbound call for the browser "AI Interview Call" page.

    Twilio will hit our existing webhook: /voice/{business_type}
    """

    twilio_from = os.environ.get("TWILIO_FROM_NUMBER", "")
    webhook_base = os.environ.get("TWILIO_WEBHOOK_BASE_URL", "")

    if not twilio_from or not webhook_base:
        return JSONResponse(
            {
                "error": "Missing TWILIO_FROM_NUMBER and/or TWILIO_WEBHOOK_BASE_URL in env (.env).",
                "detail": "Set TWILIO_FROM_NUMBER and TWILIO_WEBHOOK_BASE_URL to enable real outbound interview calls.",
            },
            status_code=400,
        )

    # We reuse the same business_type webhook logic.
    # business_type=company uses GREETING/FAQ + transfer detection in /voice/company.
    business_type = "company"

    # Use contact_id=0 because this flow is not campaign-based.
    try:
        call_sid = create_outbound_call(
            to_phone=payload.caller_number,
            from_phone=twilio_from,
            webhook_base_url=webhook_base,
            business_type=business_type,
            contact_id=0,
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

    # The admin UI can fetch transcript using /transcript/{call_sid}
    return JSONResponse({"call_sid": call_sid, "business_type": business_type, "simulated": False})

