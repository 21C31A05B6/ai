# TODO

- [ ] Inspect current timestamp writes/reads in `app/database.py` (UTC) and identify where to add IST “started time”.
- [ ] Implement IST timestamp formatting helper (exact format) inside `app/database.py`.
- [ ] Update all DB writer functions to store IST for:
  - call session: started_at, updated_at
  - call logs: timestamp
  - campaign tables: created_at/updated_at
- [ ] Ensure API responses (`/logs`, `/calls`, `/transcript/*`, campaign report) return the IST fields as “started time” consistently.
- [x] Run a quick sanity check by starting the server and verifying JSON timestamps look like `YYYY-MM-DD HH:MM:SS` in IST.


