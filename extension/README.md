# Draft reader extension (local, unpacked)

Read-only. It copies what the Yahoo draft room receives (WebSocket, fetch, XHR) to `http://localhost:8000/api/capture`. It never clicks and never sends data to Yahoo.

Install:
1. Open `chrome://extensions`.
2. Turn on "Developer mode".
3. Click "Load unpacked". Select this `extension/` folder.

Check: `curl localhost:8000/api/capture/stats`. Raw data: `data/raw/draft_capture/{league_id}/{YYYYMMDD}.jsonl`, one folder per draft (league id from the draft room URL). Load into the DB: `make draft-ingest`.
