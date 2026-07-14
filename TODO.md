# TODO

## Phase 1 — Repo understanding / safety
- [x] Read existing Twilio webhook flow (app/main.py)
- [x] Read decision/FAQ logic (app/ai_logic.py)
- [x] Read DB schema & transcript helpers (app/database.py)
- [x] Read admin UI (app/static/index.html)

## Phase 2 — Campaign import + DB linkage
- [ ] Extend DB schema for contacts + outbound campaign call mapping
- [x] Add CSV parsing helper (app/campaign_logic.py)
- [ ] Add CSV upload endpoint

- [ ] Add outbound start campaign + dialer
- [ ] Add Twilio outbound integration (REST) + metadata linkage
- [ ] Update admin UI to show name + phone with calls

- [ ] Add CSV upload + parsing endpoint
- [ ] Add endpoints to start campaign and dial next contact

## Phase 3 — Twilio outbound dialing
- [ ] Add Twilio REST client integration (env vars)
- [ ] Initiate outbound calls and associate Twilio CallSid with contact
- [ ] Ensure inbound webhook logs include contact name + phone

## Phase 4 — Admin UI updates
- [ ] Update /calls and/or add campaign-specific view to display contact name + phone
- [ ] Ensure transcript endpoints include contact name + phone

## Phase 5 — Testing
- [ ] Start server locally
- [ ] Upload sample CSV
- [ ] Trigger campaign start (dry test if needed)
- [ ] Verify DB records + transcript rendering

