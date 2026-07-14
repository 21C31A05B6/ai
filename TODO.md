# TODO

## Phase 1 — Repo understanding / safety
- [x] Read existing Twilio webhook flow (app/main.py)
- [x] Read decision/FAQ logic (app/ai_logic.py)
- [x] Read DB schema & transcript helpers (app/database.py)
- [x] Read admin UI (app/static/index.html)

## Phase 2 — Campaign import + DB linkage
- [x] Extend DB schema for contacts + outbound campaign call mapping
- [x] Add CSV parsing helper (app/campaign_logic.py)
- [x] Add CSV upload endpoint
- [x] Add outbound start campaign + dialer
- [x] Add Twilio outbound integration (REST) + metadata linkage
- [x] Update admin UI to show name + phone with calls
- [x] Add CSV upload + parsing endpoint
- [x] Add endpoints to start campaign and dial next contact

## Phase 3 — Twilio outbound dialing
- [x] Add Twilio REST client integration (env vars)
- [x] Initiate outbound calls and associate Twilio CallSid with contact
- [x] Ensure inbound webhook logs include contact name + phone

## Phase 4 — Admin UI updates
- [x] Update /calls and/or add campaign-specific view to display contact name + phone
- [x] Ensure transcript endpoints include contact name + phone

## Phase 5 — Testing
- [x] Start server locally
- [x] Upload sample CSV
- [x] Trigger campaign start (dry test if needed)
- [x] Verify DB records + transcript rendering


