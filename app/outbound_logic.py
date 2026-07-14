import os
from typing import Optional

try:
    from twilio.rest import Client as TwilioRestClient
except Exception:
    TwilioRestClient = None


def get_twilio_client() -> Optional[object]:
    """Create Twilio REST client from env vars.

    Required env vars:
      TWILIO_ACCOUNT_SID
      TWILIO_AUTH_TOKEN

    Returns None if not configured.
    """
    if TwilioRestClient is None:
        return None

    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not account_sid or not auth_token:
        return None

    return TwilioRestClient(account_sid, auth_token)


def normalize_outgoing_to(from_number: str, to_number: str) -> tuple[str, str]:
    return (str(from_number).strip(), str(to_number).strip())


def create_outbound_call(
    *,
    to_phone: str,
    from_phone: str,
    webhook_base_url: str,
    business_type: str,
    contact_id: int,
    timeout_seconds: int = 30,
) -> str:
    """Initiate outbound call via Twilio REST.

    webhook_base_url example: https://your-domain.com

    Webhook URL sent to Twilio:
      {webhook_base_url}/voice/{business_type}?contact_id=...&campaign_contact_id=...

    Returns Twilio CallSid.
    """
    client = get_twilio_client()
    if client is None:
        raise RuntimeError(
            "Twilio REST client not configured. Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN."
        )

    if not webhook_base_url:
        raise RuntimeError("Missing TWILIO_WEBHOOK_BASE_URL")

    webhook_base_url = webhook_base_url.rstrip("/")

    url = (
        f"{webhook_base_url}/voice/{business_type}"
        f"?contact_id={contact_id}"
        f"&campaign_contact_id={contact_id}"
        f"&source=outbound"
    )

    call = client.calls.create(
        to=to_phone,
        from_=from_phone,
        url=url,
        timeout=timeout_seconds,
    )

    return call.sid

