import os
from typing import List, Optional, Tuple

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from app.campaign_logic import parse_contacts_from_bytes
from app.outbound_logic import create_outbound_call
from app.database import (
    init_db,
    create_campaign,
    add_campaign_contacts,
    get_next_pending_contact,
    mark_contact_status,
    get_all_campaigns,
    get_campaign_contacts_with_calls,
    get_campaign_report,
    set_call_contact_map,
    create_call_session_for_contact,
)

router = APIRouter(prefix="/campaign", tags=["campaign"])


# ---------------------------------------------------------------------------
# Import contacts
# ---------------------------------------------------------------------------

@router.post("/import")
async def import_campaign_contacts(
    name: str = Form(...),
    file: UploadFile = File(...),
):
    """Import contacts from CSV **or** Excel (.xlsx).

    CSV/Excel must have columns:  name (optional),  phone (required).

    Accepted phone column headers: phone, mobile, mobile_number, phone_number, contact, number, cell, telephone
    Accepted name column headers:  name, full_name, candidate_name, customer_name, first_name
    """
    data = await file.read()
    filename = file.filename or "upload.csv"

    try:
        contacts: List[Tuple[str, str]] = parse_contacts_from_bytes(data, filename)
    except (ValueError, RuntimeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    init_db()
    campaign_id = create_campaign(name)
    add_campaign_contacts(campaign_id, contacts)

    return JSONResponse({
        "campaign_id": campaign_id,
        "campaign_name": name,
        "imported_contacts": len(contacts),
    })


# ---------------------------------------------------------------------------
# List campaigns
# ---------------------------------------------------------------------------

@router.get("/list")
def list_campaigns():
    """Return all campaigns with contact counts and status breakdown."""
    return JSONResponse(get_all_campaigns())


# ---------------------------------------------------------------------------
# Contacts for a campaign
# ---------------------------------------------------------------------------

@router.get("/{campaign_id}/contacts")
def get_contacts(campaign_id: int):
    """All contacts for a campaign with call status."""
    return JSONResponse(get_campaign_contacts_with_calls(campaign_id))


# ---------------------------------------------------------------------------
# Full campaign report (name + phone + conversation)
# ---------------------------------------------------------------------------

@router.get("/{campaign_id}/report")
def campaign_report(campaign_id: int):
    """Full report: each contact with their complete Q&A conversation."""
    return JSONResponse(get_campaign_report(campaign_id))


# ---------------------------------------------------------------------------
# Start outbound calls (real Twilio)
# ---------------------------------------------------------------------------

@router.post("/{campaign_id}/call-all")
async def call_all_contacts(
    campaign_id: int,
    max_calls: int = Form(default=50),
):
    """
    Trigger REAL outbound Twilio calls to all pending contacts in this campaign.

    Requires env vars:
      TWILIO_ACCOUNT_SID
      TWILIO_AUTH_TOKEN
      TWILIO_FROM_NUMBER        — your Twilio phone number e.g. +14155551234
      TWILIO_WEBHOOK_BASE_URL   — public URL for your server e.g. https://xxx.ngrok.io
    """
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    from_phone = os.environ.get("TWILIO_FROM_NUMBER", "")
    webhook_base = os.environ.get("TWILIO_WEBHOOK_BASE_URL", "")

    use_simulation = not (account_sid and auth_token and from_phone and webhook_base)

    called = []
    failed = []

    for _ in range(max_calls):
        contact = get_next_pending_contact(campaign_id)
        if not contact:
            break

        contact_id, contact_name, contact_phone = contact
        mark_contact_status(campaign_id, contact_id, "calling")

        try:
            if use_simulation:
                from app.campaign_simulation_runner import run_conversation_simulation
                call_sid = run_conversation_simulation(
                    campaign_id=campaign_id,
                    campaign_contact_id=contact_id,
                    business_type="company",
                )
            else:
                call_sid = create_outbound_call(
                    to_phone=contact_phone,
                    from_phone=from_phone,
                    webhook_base_url=webhook_base,
                    business_type="company",
                    contact_id=contact_id,
                )

                # Map the Twilio CallSid back to this contact
                set_call_contact_map(
                    call_sid=call_sid,
                    campaign_id=campaign_id,
                    campaign_contact_id=contact_id,
                    contact_name=contact_name,
                    contact_phone=contact_phone,
                )

                mark_contact_status(campaign_id, contact_id, "called")

            called.append({
                "contact_id": contact_id,
                "name": contact_name,
                "phone": contact_phone,
                "call_sid": call_sid,
            })

        except Exception as exc:
            mark_contact_status(campaign_id, contact_id, "failed")
            failed.append({
                "contact_id": contact_id,
                "name": contact_name,
                "phone": contact_phone,
                "error": str(exc),
            })

    return JSONResponse({
        "campaign_id": campaign_id,
        "calls_initiated": len(called),
        "calls_failed": len(failed),
        "called": called,
        "failed": failed,
        "simulated": use_simulation,
    })


# ---------------------------------------------------------------------------
# Call a single contact
# ---------------------------------------------------------------------------

@router.post("/{campaign_id}/call-one/{contact_id}")
async def call_one_contact(campaign_id: int, contact_id: int):
    """Trigger a single outbound Twilio call to one contact."""
    from app.database import get_campaign_contact_by_id

    contact = get_campaign_contact_by_id(campaign_id, contact_id)
    if not contact:
        return JSONResponse({"error": "Contact not found"}, status_code=404)

    contact_name, contact_phone = contact

    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    from_phone = os.environ.get("TWILIO_FROM_NUMBER", "")
    webhook_base = os.environ.get("TWILIO_WEBHOOK_BASE_URL", "")

    use_simulation = not (account_sid and auth_token and from_phone and webhook_base)

    try:
        if use_simulation:
            from app.campaign_simulation_runner import run_conversation_simulation
            call_sid = run_conversation_simulation(
                campaign_id=campaign_id,
                campaign_contact_id=contact_id,
                business_type="company",
            )
        else:
            call_sid = create_outbound_call(
                to_phone=contact_phone,
                from_phone=from_phone,
                webhook_base_url=webhook_base,
                business_type="company",
                contact_id=contact_id,
            )
            set_call_contact_map(
                call_sid=call_sid,
                campaign_id=campaign_id,
                campaign_contact_id=contact_id,
                contact_name=contact_name,
                contact_phone=contact_phone,
            )
            mark_contact_status(campaign_id, contact_id, "called")
        return JSONResponse({
            "call_sid": call_sid,
            "contact_name": contact_name,
            "contact_phone": contact_phone,
            "simulated": use_simulation,
        })
    except Exception as exc:
        mark_contact_status(campaign_id, contact_id, "failed")
        return JSONResponse({"error": str(exc)}, status_code=500)
