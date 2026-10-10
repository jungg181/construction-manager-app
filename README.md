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
