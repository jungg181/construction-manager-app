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
