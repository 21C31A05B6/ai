from dotenv import load_dotenv
load_dotenv()  # Load .env before anything else reads os.environ

import base64
import json
import os
import wave
from fastapi import FastAPI, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from twilio.twiml.voice_response import VoiceResponse, Gather

from datetime import datetime
from app.ai_logic import get_answer, wants_human
from app.faq_data import GREETING, FAREWELL
from app.database import (
    init_db,
    log_turn,
    update_call_status,
    get_all_logs,
    get_all_call_sids,
    get_transcript,
    get_transcript_as_text,
    get_campaign_contact_by_id,
    set_call_contact_map,
    create_call_session_for_contact,
    get_all_campaigns,
    get_campaign_contacts_with_calls,
    get_campaign_report,
    mark_contact_status,
    get_contact_by_id_only,
)


from app.campaign_endpoints import router as campaign_router
from app.campaign_simulation_runner import run_conversation_simulation




AUDIO_DIR = os.path.join(os.path.dirname(__file__), 'streamed_audio')
TWILIO_MEDIA_STREAM_URL = os.environ.get('TWILIO_MEDIA_STREAM_URL')

if not os.path.exists(AUDIO_DIR):
    os.makedirs(AUDIO_DIR, exist_ok=True)

stream_sessions = {}

app = FastAPI(title="AI Voice Agent")

app.include_router(campaign_router)


HUMAN_TRANSFER_NUMBER = os.environ.get("HUMAN_TRANSFER_NUMBER", "+10000000000")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

init_db()


@app.get("/health")
def health():
    return {"status": "AI Voice Agent is running"}


@app.get("/", response_class=HTMLResponse)
def homepage():
    with open("app/static/user.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard():
    with open("app/static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.post("/simulate-call/start")
async def simulate_call_start(payload: dict):

    caller_number = payload.get('caller_number', 'unknown')
    call_sid = f"SIM{int(datetime.utcnow().timestamp())}"
    greeting = GREETING
    update_call_status(call_sid, caller_number, 'company', 'active')
    log_turn(call_sid, caller_number, 'company', 'CALL STARTED', greeting, transferred=False)
    return JSONResponse({
        "call_sid": call_sid,
        "caller_number": caller_number,
        "business_type": "company",
        "greeting": greeting,
    })


@app.post("/simulate-call/question")
async def simulate_call_question(payload: dict):
    call_sid = payload.get('call_sid')
    caller_number = payload.get('caller_number', 'unknown')
    user_text = payload.get('user_text', '')
    if not call_sid:
        return JSONResponse({"detail": "call_sid is required"}, status_code=400)
    if not user_text.strip():
        return JSONResponse({"detail": "user_text is required"}, status_code=400)

    if wants_human(user_text):
        answer = "Certainly. Please hold while I transfer your call."
        transferred = True
        update_call_status(call_sid, caller_number, 'company', 'transferred')
    else:
        answer, _ = get_answer('company', user_text)
        transferred = False
        update_call_status(call_sid, caller_number, 'company', 'active')

    log_turn(call_sid, caller_number, 'company', user_text, answer, transferred=transferred)
    return JSONResponse({
        "call_sid": call_sid,
        "caller_number": caller_number,
        "business_type": "company",
        "user_text": user_text,
        "answer": answer,
        "transferred": transferred,
    })


@app.post("/simulate-call/end")
async def simulate_call_end(payload: dict):
    call_sid = payload.get('call_sid')
    caller_number = payload.get('caller_number', 'unknown')
    if not call_sid:
        return JSONResponse({"detail": "call_sid is required"}, status_code=400)

    update_call_status(call_sid, caller_number, 'company', 'ended')
    log_turn(call_sid, caller_number, 'company', '[CALL ENDED]', 'Call ended by user.', transferred=False)
    return JSONResponse({
        "call_sid": call_sid,
        "status": "ended",
    })


@app.post("/voice/{business_type}")
async def voice_entry(
    business_type: str,
    CallSid: str = Form(default="test-call"),
    From: str = Form(default="unknown"),
    contact_id: int = 0,
):

    """
    Twilio hits this URL the moment a call comes in.
    Point your Twilio number's 'A Call Comes In' webhook here:
    https://YOUR_DOMAIN/voice/support   (or hospital / college / hotel / restaurant)
    """
    # If this is an outbound call, attach imported contact metadata.
    # We map the inbound webhook (CallSid) back to the imported contact.
    if contact_id:
        # Retrieve the contact and campaign details dynamically
        contact = get_contact_by_id_only(contact_id)
        if contact:
            contact_name = contact.get("name") or ""
            contact_phone = contact.get("phone") or ""
            campaign_id = contact.get("campaign_id") or 0

            set_call_contact_map(
                call_sid=CallSid,
                campaign_id=campaign_id,
                campaign_contact_id=contact_id,
                contact_name=contact_name,
                contact_phone=contact_phone,
            )

    vr = VoiceResponse()
    if TWILIO_MEDIA_STREAM_URL:
        vr.redirect(f"/voice/{business_type}")

    gather = Gather(
        input="speech",
        action=f"/gather/{business_type}",
        method="POST",
        speech_timeout="auto",
        language="en-IN",
    )
    gather.say(GREETING, voice="Polly.Aditi")
    vr.append(gather)

    return Response(content=str(vr), media_type="application/xml")


@app.post("/gather/{business_type}")
async def gather_response(business_type: str,
                           SpeechResult: str = Form(default=""),
                           CallSid: str = Form(default="test-call"),
                           From: str = Form(default="unknown")):
    """
    Twilio posts here with what the caller said (converted to text automatically
    by Twilio's built-in speech recognition -- no separate Whisper/Deepgram call needed).
    """
    vr = VoiceResponse()
    user_text = SpeechResult or ""

    if not user_text.strip():
        gather = Gather(input="speech", action=f"/gather/{business_type}",
                         method="POST", speech_timeout="auto", language="en-IN")
        gather.say("Sorry, I didn't catch that. Could you say that again?", voice="Polly.Aditi")
        vr.append(gather)
        return Response(content=str(vr), media_type="application/xml")

    if wants_human(user_text):
    
        vr.dial(HUMAN_TRANSFER_NUMBER)
        log_turn(CallSid, From, business_type, user_text, "TRANSFERRED TO HUMAN", transferred=True)
        return Response(content=str(vr), media_type="application/xml")

    answer, matched = get_answer(business_type, user_text)
    log_turn(CallSid, From, business_type, user_text, answer, transferred=False)

    gather = Gather(input="speech", action=f"/gather/{business_type}",
                     method="POST", speech_timeout="auto", language="en-IN")
    gather.say(answer, voice="Polly.Aditi")
    gather.say("Is there anything else I can help you with?", voice="Polly.Aditi")
    vr.append(gather)
    vr.say(FAREWELL, voice="Polly.Aditi")
    vr.hangup()
    update_call_status(CallSid, From, business_type, 'ended')
    return Response(content=str(vr), media_type="application/xml")


@app.get("/logs")
def view_logs():
    """Every single turn from every call, newest first."""
    return JSONResponse(get_all_logs())


@app.get("/calls")
def view_calls():
    """One row per call (not per turn) -- a quick index of every call received."""
    return JSONResponse(get_all_call_sids())


@app.get("/transcript/{call_sid}")
def view_transcript_json(call_sid: str):
    """The full Q&A pairs for one call, in clean JSON: [{question, answer}, ...]."""
    return JSONResponse(get_transcript(call_sid))


@app.get("/transcript/{call_sid}/text")
def view_transcript_text(call_sid: str):
    """Same transcript, formatted as readable text -- good for saving as a .txt file."""
    return Response(content=get_transcript_as_text(call_sid), media_type="text/plain")


# ---------------------------------------------------------------------------
# Twilio call-status callback — fired when an outbound call ends
# ---------------------------------------------------------------------------
@app.post("/call-status")
async def call_status_callback(
    CallSid: str = Form(default=""),
    CallStatus: str = Form(default=""),
    To: str = Form(default=""),
    From: str = Form(default=""),
):
    """
    Twilio posts here when an outbound call changes status (completed, busy,
    no-answer, failed).  We use it to mark the call session as ended.
    """
    if CallSid:
        status_map = {
            "completed": "ended",
            "busy": "ended",
            "no-answer": "ended",
            "failed": "ended",
            "canceled": "ended",
        }
        db_status = status_map.get(CallStatus, "ended")
        update_call_status(CallSid, To or From, "company", db_status)
    return Response(content="", media_type="text/plain")


# ---------------------------------------------------------------------------
# Campaign summary endpoints (also exposed via campaign_router but duplicated
# here so admin JS can call /campaign/* directly)
# ---------------------------------------------------------------------------
@app.get("/campaigns")
def list_all_campaigns():
    """All campaigns with contact counts."""
    return JSONResponse(get_all_campaigns())

@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    stream_sid = None
    wave_writer = None
    try:
        while True:
            message = await websocket.receive_text()
            payload = json.loads(message)
            event = payload.get('event')

            if event == 'start':
                details = payload.get('start', {})
                stream_sid = details.get('streamSid')
                sample_rate = int(details.get('sampleRate', 8000))
                call_sid = details.get('callSid', 'unknown')
                filename = f"{call_sid}_{stream_sid}.wav"
                filepath = os.path.join(AUDIO_DIR, filename)
                wave_writer = wave.open(filepath, 'wb')
                wave_writer.setnchannels(1)
                wave_writer.setsampwidth(2)
                wave_writer.setframerate(sample_rate)
                stream_sessions[stream_sid] = wave_writer

            elif event == 'media':
                if not stream_sid or stream_sid not in stream_sessions:
                    continue
                media = payload.get('media', {})
                encoded = media.get('payload')
                if encoded:
                    audio_data = base64.b64decode(encoded)
                    stream_sessions[stream_sid].writeframes(audio_data)

            elif event in ('stop', 'closed'):
                if stream_sid and stream_sid in stream_sessions:
                    stream_sessions.pop(stream_sid).close()
                    wave_writer = None
    except WebSocketDisconnect:
        if stream_sid and stream_sid in stream_sessions:
            stream_sessions.pop(stream_sid).close()
