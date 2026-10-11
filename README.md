# Construction Manager (standalone)

A standalone rebuild of the "Construction Manager" site-management app:
11 tabs — Dashboard, Sites, Map & Plans, Workers, Timecards, Incidents,
Daily Logs, Labour, Materials, QA/QC, Data & Restore — plus QR-code
clock-in/out for field workers.

## Run

```bash
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000

## Notes

- Data is stored in `data.json` (created on first run with 2 demo sites
  and 3 demo workers). Download a JSON backup anytime from the Data tab.
- Uploaded photos/plans go to `static/uploads/`.
- QR attendance: on the Workers tab click **Attendance QR**, pick a jobsite
  and action — the generated QR is valid for 10 minutes. Workers scan it
  with their phone, pick their name, and confirm (geolocation captured).
- Maps use Leaflet with free Esri World Imagery tiles (CDN).
- No login — single-user local tool.

## On Site worker app (`/onsite`)

A mobile-first page for field workers (open it on the phone's browser):

1. Worker **self-registers once** on their own phone: full name, mobile phone,
   trade, employment type. The phone is matched by normalized phone number, so
   reinstalling the app re-links to the same worker record instead of making a
   duplicate. The phone remembers the worker afterwards (localStorage).
2. Taps **Scan QR** and points the camera at the supervisor's Attendance QR
   (in-page scanner; if the camera is blocked, the code can be pasted manually).
3. A confirm card shows the site + Clock In/Out action; Confirm captures GPS
   and posts the timecard.
4. **Share my live location** toggle (off by default, only enabled while
   clocked in) sends the phone's position to the server every 60 seconds.
5. "Switch worker" in the header clears the phone's registration.

Workers who registered themselves show a purple **Self** badge in the admin
Workers list; admins can still register/edit/delete any worker as before.
   Sharing stops automatically on clock-out.
5. "My timecards" shows the last 7 days.

Admin side: the Map & Plans **Active Personnel** layer shows 🟢 live pins
("updated X min ago", refreshed every 60s), falling back to clock-in GPS pins
when a worker is not sharing. The Workers tab shows a pulsing **● Live**
badge next to clocked-in workers who shared a position within 15 minutes.

### Offline support

Construction sites often have no internet. The On Site app keeps working:

- A service worker (`/sw.js`) caches the app page, stylesheet, and the QR
  scanner library after the first online load, so `/onsite` opens offline.
- An **Offline** banner appears when the phone loses connection.
- **Offline clock:** scanning a QR offline shows Clock In / Clock Out buttons
  (the worker picks the action, since the QR can't be validated). The action
  is queued in the phone with the scan's local timestamp and GPS. On
  reconnect it syncs via `POST /api/sync-clock`; the server only accepts it
  if the scan happened while the QR was valid (`created_at <= client_at <=
  expires_at`) — a scan of an already-expired QR is rejected. Synced records
  get an **Offline** badge in the admin Timecards table and use the phone's
  timestamp, not the sync time.
- **Offline locations:** while sharing is on but offline, positions are
  buffered on the phone (up to 500, oldest dropped) and uploaded in one
  batch (`POST /api/location-batch`) on reconnect.
- Registration is online-only (one-time): offline with no registered identity
  shows "Connect to the internet once to register".

Note: the server clock and the phone clock should be roughly in sync;
the QR validity window is checked against the phone's scan timestamp.
