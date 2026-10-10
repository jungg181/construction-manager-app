"""Construction Manager - standalone site management web app (Flask)."""
import os
import io
import csv
import json
import copy
import uuid
from datetime import datetime, date, timedelta

from flask import (Flask, render_template, request, redirect, url_for,
                   jsonify, send_file, abort, flash)
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data.json')
UPLOAD_DIR = os.path.join(BASE_DIR, 'static', 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = 'site-manager-local-key'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

COLLECTIONS = ['sites', 'workers', 'timecards', 'incidents', 'daily_logs',
               'labour', 'materials', 'defects', 'qa_checks', 'pins',
               'plans', 'qr_tokens', 'snapshots', 'trash', 'dispatches']


def new_id():
    return uuid.uuid4().hex[:8]


def now_iso():
    return datetime.now().isoformat(timespec='seconds')


def today():
    return date.today()


def parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def seed(db):
    db['sites'] = [
        {'id': 'site-lges', 'name': 'LGES', 'photo_url': '',
         'lat': 33.28844, 'lng': -111.55389,
         'address': "33°17'18.4\"N 111°33'14.0\"W, Queen Creek, AZ",
         'pm': 'Jake', 'start_date': '2024-11-01',
         'target_date': '2026-12-12', 'status': 'active'},
        {'id': 'site-office', 'name': 'Office', 'photo_url': '',
         'lat': None, 'lng': None, 'address': '',
         'pm': '', 'start_date': '', 'target_date': '', 'status': 'active'},
    ]
    db['workers'] = [
        {'id': 'wkr-demo1', 'name': 'Alex Rivera', 'email': 'alex@example.com',
         'phone': '+14805550101', 'trade': 'Electrician',
         'employment_type': 'Direct Team', 'hourly_rate': 32.0,
         'site_id': 'site-lges', 'status': 'active',
         'emergency_contact': 'Maria Rivera', 'photo_url': '',
         'created_at': now_iso()},
        {'id': 'wkr-demo2', 'name': 'Sam Chen', 'email': 'sam@example.com',
         'phone': '+14805550102', 'trade': 'Carpenter',
         'employment_type': 'Contract', 'hourly_rate': 28.5,
         'site_id': 'site-lges', 'status': 'active',
         'emergency_contact': 'Li Chen', 'photo_url': '',
         'created_at': now_iso()},
        {'id': 'wkr-demo3', 'name': 'Jordan Lee', 'email': 'jordan@example.com',
         'phone': '+14805550103', 'trade': 'Laborer',
         'employment_type': 'Contract', 'hourly_rate': 24.0,
         'site_id': 'site-office', 'status': 'on_leave',
         'emergency_contact': 'Pat Lee', 'photo_url': '',
         'created_at': now_iso()},
    ]


def load_db():
    if not os.path.exists(DB_PATH):
        db = {c: [] for c in COLLECTIONS}
        seed(db)
        with open(DB_PATH, 'w') as f:
            json.dump(db, f, indent=2)
        return db
    with open(DB_PATH) as f:
        db = json.load(f)
    for c in COLLECTIONS:
        db.setdefault(c, [])
    return db


def save_db():
    with open(DB_PATH, 'w') as f:
        json.dump(DB, f, indent=2)


DB = load_db()


# ---------- lookup / computed helpers ----------

def find(coll, _id):
    return next((r for r in DB[coll] if r.get('id') == _id), None)


def site_name(site_id):
    s = find('sites', site_id)
    return s['name'] if s else '—'


def worker_name(worker_id):
    w = find('workers', worker_id)
    return w['name'] if w else '—'


def compute_hours(clock_in_iso, clock_out_iso):
    """Shift hours; 1h meal break auto-deducted for shifts >= 5h."""
    ci, co = parse_iso(clock_in_iso), parse_iso(clock_out_iso)
    if not ci or not co:
        return 0.0
    h = (co - ci).total_seconds() / 3600.0
    if h >= 5:
        h -= 1.0
    return round(max(h, 0.0), 2)


def days_remaining(target_date):
    try:
        d = date.fromisoformat(target_date) - today()
        return d.days
    except (ValueError, TypeError):
        return None


def is_low_stock(m):
    try:
        return float(m.get('quantity') or 0) <= float(m.get('reorder_threshold') or 0)
    except (ValueError, TypeError):
        return False


def open_timecard(worker_id, site_id=None):
    for t in DB['timecards']:
        if t['worker_id'] == worker_id and t['status'] == 'clocked_in':
            if site_id is None or t['site_id'] == site_id:
                return t
    return None


def trash_record(coll, record):
    DB['trash'].append({
        'type': coll,
        'record': record,
        'deleted_at': now_iso(),
        'deleted_by': 'Admin',
    })


def remove_from(coll, _id, to_trash=True):
    rec = find(coll, _id)
    if not rec:
        return False
    DB[coll] = [r for r in DB[coll] if r.get('id') != _id]
    if to_trash:
        trash_record(coll, rec)
    save_db()
    return True


def save_upload(f):
    if not f or not f.filename:
        return ''
    name = secure_filename(f.filename)
    fname = f"{uuid.uuid4().hex[:8]}_{name}"
    f.save(os.path.join(UPLOAD_DIR, fname))
    return '/static/uploads/' + fname


def gmaps_link(lat, lng):
    if lat in (None, '') or lng in (None, ''):
        return None
    return f"https://www.google.com/maps?q={lat},{lng}"


def needs_attention_count():
    return sum(1 for t in DB['timecards'] if t.get('status') == 'clocked_out')


def open_defects_count():
    return sum(1 for d in DB['defects'] if d.get('status') == 'open')


def fmt_dt(iso):
    dt = parse_iso(iso)
    return dt.strftime('%m/%d %I:%M %p') if dt else '—'


app.jinja_env.globals.update(
    site_name=site_name, worker_name=worker_name, fmt_dt=fmt_dt,
    gmaps_link=gmaps_link, compute_hours=compute_hours,
    days_remaining=days_remaining, today=today,
)

NAV = [
    ('dashboard', 'Dashboard', '/'),
    ('sites', 'Sites', '/sites'),
    ('blueprints', 'Map & Plans', '/blueprints'),
    ('workers', 'Workers', '/workers'),
    ('timecards', 'Timecards', '/timecards'),
    ('incidents', 'Incidents', '/incidents'),
    ('daily_logs', 'Daily Logs', '/daily-logs'),
    ('labour', 'Labour', '/labour'),
    ('materials', 'Materials', '/materials'),
    ('qa', 'QA/QC', '/qa'),
    ('data', 'Data', '/data'),
]


@app.context_processor
def inject_nav():
    return dict(nav=NAV, active_tab=request.endpoint,
                attention=needs_attention_count(),
                open_defects=open_defects_count())


# ================= DASHBOARD =================

@app.route('/')
def dashboard():
    open_incidents = sum(1 for i in DB['incidents'] if i.get('status') == 'open')
    open_defects = open_defects_count()
    low_stock = sum(1 for m in DB['materials'] if is_low_stock(m))
    tdy = today().isoformat()
    on_site = {t['worker_id'] for t in DB['timecards']
               if (t.get('clock_in') or '').startswith(tdy)}
    sites = []
    for s in DB['sites']:
        sites.append({
            'site': s,
            'days': days_remaining(s.get('target_date') or ''),
            'incidents': sum(1 for i in DB['incidents'] if i['site_id'] == s['id'] and i.get('status') == 'open'),
            'defects': sum(1 for d in DB['defects'] if d['site_id'] == s['id'] and d.get('status') == 'open'),
        })
    recent_incidents = sorted(DB['incidents'], key=lambda i: i.get('created_at', ''), reverse=True)[:5]
    overdue = [d for d in DB['defects']
               if d.get('status') == 'open' and d.get('due_date') and d['due_date'] < tdy]
    return render_template('dashboard.html',
                           open_incidents=open_incidents, open_defects=open_defects,
                           low_stock=low_stock, on_site=len(on_site),
                           sites=sites, recent_incidents=recent_incidents,
                           overdue=overdue)


# ================= SITES =================

SITE_STATUSES = ['active', 'on_hold', 'completed']


@app.route('/sites')
def sites():
    q = (request.args.get('q') or '').lower()
    status = request.args.get('status') or 'all'
    rows = []
    for s in DB['sites']:
        if status != 'all' and s.get('status') != status:
            continue
        if q and q not in f"{s['name']} {s.get('address','')} {s.get('pm','')}".lower():
            continue
        tdy = today().isoformat()
        rows.append({
            'site': s,
            'days': days_remaining(s.get('target_date') or ''),
            'incidents': sum(1 for i in DB['incidents'] if i['site_id'] == s['id'] and i.get('status') == 'open'),
            'defects': sum(1 for d in DB['defects'] if d['site_id'] == s['id'] and d.get('status') == 'open'),
            'low_stock': sum(1 for m in DB['materials'] if m['site_id'] == s['id'] and is_low_stock(m)),
            'workers': sum(1 for t in DB['timecards']
                           if t['site_id'] == s['id'] and (t.get('clock_in') or '').startswith(tdy)),
        })
    counts = {st: sum(1 for s in DB['sites'] if s.get('status') == st) for st in SITE_STATUSES}
    return render_template('sites.html', rows=rows, q=request.args.get('q', ''),
                           status=status, counts=counts, total=len(DB['sites']))


@app.route('/sites/new', methods=['GET', 'POST'])
def site_new():
    if request.method == 'POST':
        s = {
            'id': new_id(),
            'name': request.form.get('name', '').strip(),
            'photo_url': save_upload(request.files.get('photo')),
            'lat': _f(request.form.get('lat')), 'lng': _f(request.form.get('lng')),
            'address': request.form.get('address', '').strip(),
            'pm': request.form.get('pm', '').strip(),
            'start_date': request.form.get('start_date', ''),
            'target_date': request.form.get('target_date', ''),
            'status': request.form.get('status', 'active'),
        }
        DB['sites'].append(s)
        save_db()
        flash(f"Site '{s['name']}' added.")
        return redirect(url_for('sites'))
    return render_template('site_form.html', site=None, statuses=SITE_STATUSES)


@app.route('/sites/<sid>/edit', methods=['GET', 'POST'])
def site_edit(sid):
    s = find('sites', sid)
    if not s:
        abort(404)
    if request.method == 'POST':
        s['name'] = request.form.get('name', '').strip()
        ph = save_upload(request.files.get('photo'))
        if ph:
            s['photo_url'] = ph
        s['lat'] = _f(request.form.get('lat'))
        s['lng'] = _f(request.form.get('lng'))
        s['address'] = request.form.get('address', '').strip()
        s['pm'] = request.form.get('pm', '').strip()
        s['start_date'] = request.form.get('start_date', '')
        s['target_date'] = request.form.get('target_date', '')
        s['status'] = request.form.get('status', 'active')
        save_db()
        flash(f"Site '{s['name']}' updated.")
        return redirect(url_for('sites'))
    return render_template('site_form.html', site=s, statuses=SITE_STATUSES)


@app.route('/sites/<sid>/delete', methods=['POST'])
def site_delete(sid):
    if remove_from('sites', sid):
        flash('Site deleted (moved to Recycle Bin).')
    return redirect(url_for('sites'))


def _f(v):
    try:
        return float(v) if v not in (None, '') else None
    except (ValueError, TypeError):
        return None


# ================= SITE MAP & PLANS =================

@app.route('/blueprints')
def blueprints():
    site_id = request.args.get('site_id') or (DB['sites'][0]['id'] if DB['sites'] else '')
    site = find('sites', site_id)
    floors = sorted({p['floor'] for p in DB['plans'] if p['site_id'] == site_id} | {'1F', '2F'})
    floor = request.args.get('floor') or floors[0]
    plan = next((p for p in DB['plans'] if p['site_id'] == site_id and p['floor'] == floor), None)
    pins = [p for p in DB['pins'] if p['site_id'] == site_id and p.get('floor') == floor]
    counts = {
        'personnel': sum(1 for t in DB['timecards']
                         if t['site_id'] == site_id and t.get('status') == 'clocked_in'
                         and t.get('clock_in_lat') not in (None, '')),
        'defect': sum(1 for p in pins if p.get('kind') == 'defect'),
        'hazard': sum(1 for p in pins if p.get('kind') == 'hazard'),
    }
    return render_template('blueprints.html', sites=DB['sites'], site=site,
                           floors=floors, floor=floor, plan=plan,
                           pins=pins, counts=counts)


@app.route('/blueprints/upload', methods=['POST'])
def plan_upload():
    site_id = request.form.get('site_id')
    floor = request.form.get('floor', '1F').strip() or '1F'
    img = save_upload(request.files.get('plan'))
    if not img:
        flash('No file uploaded.')
        return redirect(url_for('blueprints', site_id=site_id))
    old = next((p for p in DB['plans'] if p['site_id'] == site_id and p['floor'] == floor), None)
    if old:
        DB['plans'].remove(old)
    DB['plans'].append({'id': new_id(), 'site_id': site_id, 'floor': floor,
                        'image_path': img})
    save_db()
    flash(f'Plan uploaded for {floor}.')
    return redirect(url_for('blueprints', site_id=site_id, floor=floor))


@app.route('/api/pins')
def api_pins():
    site_id = request.args.get('site_id')
    floor = request.args.get('floor')
    pins = [p for p in DB['pins']
            if (not site_id or p['site_id'] == site_id)
            and (not floor or p.get('floor') == floor)]
    return jsonify(pins)


@app.route('/api/pins', methods=['POST'])
def api_pin_add():
    d = request.get_json(force=True)
    pin = {'id': new_id(), 'site_id': d.get('site_id'), 'floor': d.get('floor', '1F'),
           'kind': d.get('kind', 'defect'), 'x': d.get('x', 0), 'y': d.get('y', 0),
           'lat': d.get('lat'), 'lng': d.get('lng'),
           'label': (d.get('label') or '').strip() or d.get('kind', 'pin').title()}
    DB['pins'].append(pin)
    save_db()
    return jsonify(pin)


@app.route('/api/pins/<pid>', methods=['DELETE'])
def api_pin_delete(pid):
    DB['pins'] = [p for p in DB['pins'] if p.get('id') != pid]
    save_db()
    return jsonify({'ok': True})


@app.route('/api/personnel')
def api_personnel():
    site_id = request.args.get('site_id')
    out = []
    for t in DB['timecards']:
        if t.get('status') != 'clocked_in':
            continue
        if site_id and t['site_id'] != site_id:
            continue
        if t.get('clock_in_lat') in (None, ''):
            continue
        out.append({'worker': worker_name(t['worker_id']),
                    'lat': t['clock_in_lat'], 'lng': t['clock_in_lng'],
                    'since': fmt_dt(t.get('clock_in'))})
    return jsonify(out)


# ================= WORKERS =================

TRADES = ['Electrician', 'Carpenter', 'Plumber', 'Laborer', 'Welder',
          'Painter', 'Mason', 'Foreman', 'Operator', 'Other']
EMP_TYPES = ['Direct Team', 'Contract']
WORKER_STATUSES = ['active', 'on_leave', 'inactive']


@app.route('/workers')
def workers():
    q = (request.args.get('q') or '').lower()
    fsite = request.args.get('site') or 'all'
    ftrade = request.args.get('trade') or 'all'
    fstatus = request.args.get('status') or 'all'
    rows = []
    for w in DB['workers']:
        if fsite != 'all' and w.get('site_id') != fsite:
            continue
        if ftrade != 'all' and w.get('trade') != ftrade:
            continue
        if fstatus != 'all' and w.get('status') != fstatus:
            continue
        if q and q not in f"{w['name']} {w.get('phone','')} {w.get('trade','')}".lower():
            continue
        w2 = dict(w)
        w2['clocked_in'] = open_timecard(w['id']) is not None
        rows.append(w2)
    total_hours = sum(t.get('hours') or compute_hours(t.get('clock_in'), t.get('clock_out'))
                      for t in DB['timecards'] if t.get('clock_out'))
    active_now = sum(1 for t in DB['timecards'] if t.get('status') == 'clocked_in')
    return render_template('workers.html', rows=rows,
                           q=request.args.get('q', ''), fsite=fsite,
                           ftrade=ftrade, fstatus=fstatus,
                           sites=DB['sites'], trades=sorted({w.get('trade') for w in DB['workers'] if w.get('trade')} | set(TRADES)),
                           total=len(DB['workers']), active_now=active_now,
                           total_hours=round(total_hours, 1))


@app.route('/workers/new', methods=['GET', 'POST'])
def worker_new():
    if request.method == 'POST':
        w = {
            'id': new_id(),
            'name': request.form.get('name', '').strip(),
            'email': request.form.get('email', '').strip(),
            'phone': request.form.get('phone', '').strip(),
            'trade': request.form.get('trade', '').strip() or 'Other',
            'employment_type': request.form.get('employment_type', 'Contract'),
            'hourly_rate': _f(request.form.get('hourly_rate')) or 0.0,
            'site_id': request.form.get('site_id') or None,
            'status': 'active',
            'emergency_contact': request.form.get('emergency_contact', '').strip(),
            'photo_url': save_upload(request.files.get('photo')),
            'created_at': now_iso(),
        }
        DB['workers'].append(w)
        save_db()
        flash(f"Worker '{w['name']}' registered.")
        return redirect(url_for('workers'))
    return render_template('worker_form.html', worker=None, sites=DB['sites'],
                           trades=TRADES, emp_types=EMP_TYPES, statuses=WORKER_STATUSES)


@app.route('/workers/<wid>/edit', methods=['GET', 'POST'])
def worker_edit(wid):
    w = find('workers', wid)
    if not w:
        abort(404)
    if request.method == 'POST':
        w['name'] = request.form.get('name', '').strip()
        w['email'] = request.form.get('email', '').strip()
        w['phone'] = request.form.get('phone', '').strip()
        w['trade'] = request.form.get('trade', '').strip() or 'Other'
        w['employment_type'] = request.form.get('employment_type', 'Contract')
        w['hourly_rate'] = _f(request.form.get('hourly_rate')) or 0.0
        w['site_id'] = request.form.get('site_id') or None
        w['status'] = request.form.get('status', 'active')
        w['emergency_contact'] = request.form.get('emergency_contact', '').strip()
        ph = save_upload(request.files.get('photo'))
        if ph:
            w['photo_url'] = ph
        save_db()
        flash(f"Worker '{w['name']}' updated.")
        return redirect(url_for('workers'))
    return render_template('worker_form.html', worker=w, sites=DB['sites'],
                           trades=TRADES, emp_types=EMP_TYPES, statuses=WORKER_STATUSES)


@app.route('/workers/<wid>/delete', methods=['POST'])
def worker_delete(wid):
    if remove_from('workers', wid):
        flash('Worker deleted (moved to Recycle Bin).')
    return redirect(url_for('workers'))


@app.route('/workers/export')
def workers_export():
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['id', 'name', 'email', 'phone', 'trade', 'employment_type',
                'hourly_rate', 'site', 'status', 'emergency_contact', 'created_at'])
    for x in DB['workers']:
        w.writerow([x.get('id'), x.get('name'), x.get('email'), x.get('phone'),
                    x.get('trade'), x.get('employment_type'), x.get('hourly_rate'),
                    site_name(x.get('site_id')), x.get('status'),
                    x.get('emergency_contact'), x.get('created_at')])
    data = io.BytesIO(buf.getvalue().encode('utf-8'))
    return send_file(data, mimetype='text/csv', as_attachment=True,
                     download_name='workers.csv')


@app.route('/api/dispatch', methods=['POST'])
def api_dispatch():
    d = request.get_json(force=True)
    rec = {'id': new_id(), 'worker_id': d.get('worker_id'),
           'message': (d.get('message') or '').strip(),
           'created_at': now_iso()}
    DB['dispatches'].append(rec)
    save_db()
    return jsonify(rec)


# ================= QR ATTENDANCE =================

@app.route('/api/qr', methods=['POST'])
def api_qr_create():
    d = request.get_json(force=True)
    token = uuid.uuid4().hex
    rec = {'token': token, 'site_id': d.get('site_id'),
           'action': d.get('action', 'clock_in'),
           'expires_at': (datetime.now() + timedelta(minutes=10)).isoformat(timespec='seconds'),
           'clock_url': request.host_url.rstrip('/') + '/clock/' + token}
    DB['qr_tokens'] = [t for t in DB['qr_tokens'] if t['token'] != token]
    DB['qr_tokens'].append(rec)
    save_db()
    return jsonify(rec)


@app.route('/qr/<token>.png')
def qr_image(token):
    try:
        import qrcode
    except ImportError:
        abort(500, 'qrcode library not installed')
    rec = next((t for t in DB['qr_tokens'] if t['token'] == token), None)
    if not rec:
        abort(404)
    img = qrcode.make(rec['clock_url'])
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')


def _valid_token(token):
    rec = next((t for t in DB['qr_tokens'] if t['token'] == token), None)
    if not rec:
        return None
    if parse_iso(rec['expires_at']) and parse_iso(rec['expires_at']) < datetime.now():
        return None
    return rec


@app.route('/clock/<token>')
def clock_page(token):
    rec = _valid_token(token)
    if not rec:
        return render_template('clock.html', error='This QR code has expired. Ask your supervisor for a new one.'), 410
    active_workers = [w for w in DB['workers'] if w.get('status') == 'active']
    return render_template('clock.html', rec=rec, site=find('sites', rec['site_id']),
                           workers=active_workers, error=None)


@app.route('/clock/<token>/confirm', methods=['POST'])
def clock_confirm(token):
    rec = _valid_token(token)
    if not rec:
        return render_template('clock.html', error='This QR code has expired.'), 410
    worker_id = request.form.get('worker_id')
    lat = request.form.get('lat') or None
    lng = request.form.get('lng') or None
    w = find('workers', worker_id)
    if not w:
        flash('Worker not found.')
        return redirect(url_for('clock_page', token=token))
    now = now_iso()
    if rec['action'] == 'clock_in':
        if open_timecard(worker_id):
            return render_template('clock_done.html', message=f"{w['name']} is already clocked in.",
                                   site=site_name(rec['site_id']))
        t = {'id': new_id(), 'worker_id': worker_id, 'site_id': rec['site_id'],
             'clock_in': now, 'clock_in_lat': lat, 'clock_in_lng': lng,
             'clock_out': None, 'clock_out_lat': None, 'clock_out_lng': None,
             'hours': 0.0, 'status': 'clocked_in', 'notes': 'QR clock-in'}
        DB['timecards'].append(t)
        save_db()
        return render_template('clock_done.html',
                               message=f"{w['name']} clocked in at {site_name(rec['site_id'])}.",
                               site=site_name(rec['site_id']))
    else:
        t = open_timecard(worker_id, rec['site_id']) or open_timecard(worker_id)
        if not t:
            return render_template('clock_done.html',
                                   message=f"No open shift found for {w['name']}.",
                                   site=site_name(rec['site_id']))
        t['clock_out'] = now
        t['clock_out_lat'] = lat
        t['clock_out_lng'] = lng
        t['hours'] = compute_hours(t['clock_in'], now)
        t['status'] = 'clocked_out'
        save_db()
        return render_template('clock_done.html',
                               message=f"{w['name']} clocked out. Shift: {t['hours']}h (pending approval).",
                               site=site_name(rec['site_id']))


# ================= TIMECARDS =================

@app.route('/timecards')
def timecards():
    fsite = request.args.get('site') or 'all'
    fstatus = request.args.get('status') or 'all'
    sort = request.args.get('sort') or 'newest'
    rows = []
    for t in DB['timecards']:
        if fsite != 'all' and t.get('site_id') != fsite:
            continue
        if fstatus != 'all' and t.get('status') != fstatus:
            continue
        rows.append(t)
    rows.sort(key=lambda t: t.get('clock_in') or '',
              reverse=(sort == 'newest'))
    total_hours = sum(t.get('hours') or compute_hours(t.get('clock_in'), t.get('clock_out'))
                      for t in rows if t.get('clock_out'))
    gps_n = sum(1 for t in rows if t.get('clock_in_lat') not in (None, ''))
    active_now = sum(1 for t in DB['timecards'] if t.get('status') == 'clocked_in')
    return render_template('timecards.html', rows=rows, fsite=fsite,
                           fstatus=fstatus, sort=sort, sites=DB['sites'],
                           total_hours=round(total_hours, 1), total=len(rows),
                           gps_pct=round(100 * gps_n / len(rows)) if rows else 0,
                           active_now=active_now, attention=needs_attention_count())


@app.route('/timecards/new', methods=['GET', 'POST'])
def timecard_new():
    if request.method == 'POST':
        t = _timecard_from_form(request.form)
        DB['timecards'].append(t)
        save_db()
        flash('Timecard logged.')
        return redirect(url_for('timecards'))
    return render_template('timecard_form.html', t=None, workers=DB['workers'], sites=DB['sites'])


def _timecard_from_form(form):
    ci_date, ci_time = form.get('date', ''), form.get('clock_in', '')
    co_time = form.get('clock_out', '')
    clock_in = f"{ci_date}T{ci_time}:00" if ci_date and ci_time else None
    clock_out = f"{ci_date}T{co_time}:00" if ci_date and co_time else None
    status = 'clocked_in'
    hours = 0.0
    if clock_out:
        hours = compute_hours(clock_in, clock_out)
        status = 'clocked_out'
    return {'id': new_id(), 'worker_id': form.get('worker_id'),
            'site_id': form.get('site_id'), 'clock_in': clock_in,
            'clock_in_lat': None, 'clock_in_lng': None,
            'clock_out': clock_out, 'clock_out_lat': None, 'clock_out_lng': None,
            'hours': hours, 'status': status,
            'notes': form.get('notes', '').strip()}


@app.route('/timecards/bulk', methods=['GET', 'POST'])
def timecard_bulk():
    if request.method == 'POST':
        n = 0
        for i in range(8):
            if not request.form.get(f'rows[{i}][worker_id]'):
                continue
            mini = {'worker_id': request.form.get(f'rows[{i}][worker_id]'),
                    'site_id': request.form.get(f'rows[{i}][site_id]'),
                    'date': request.form.get(f'rows[{i}][date]'),
                    'clock_in': request.form.get(f'rows[{i}][clock_in]'),
                    'clock_out': request.form.get(f'rows[{i}][clock_out]'),
                    'notes': request.form.get(f'rows[{i}][notes]', '')}
            t = _timecard_from_form(mini)
            DB['timecards'].append(t)
            n += 1
        save_db()
        flash(f'{n} timecards added.')
        return redirect(url_for('timecards'))
    return render_template('timecard_bulk.html', workers=DB['workers'], sites=DB['sites'],
                           today=today().isoformat())


@app.route('/timecards/<tid>/edit', methods=['GET', 'POST'])
def timecard_edit(tid):
    t = find('timecards', tid)
    if not t:
        abort(404)
    if request.method == 'POST':
        upd = _timecard_from_form(request.form)
        t['worker_id'] = upd['worker_id'] or t['worker_id']
        t['site_id'] = upd['site_id'] or t['site_id']
        if upd['clock_in']:
            t['clock_in'] = upd['clock_in']
        if upd['clock_out']:
            t['clock_out'] = upd['clock_out']
            t['hours'] = upd['hours']
            if t['status'] == 'clocked_in':
                t['status'] = 'clocked_out'
        t['notes'] = upd['notes']
        save_db()
        flash('Timecard updated.')
        return redirect(url_for('timecards'))
    return render_template('timecard_form.html', t=t, workers=DB['workers'], sites=DB['sites'])


@app.route('/timecards/<tid>/approve', methods=['POST'])
def timecard_approve(tid):
    t = find('timecards', tid)
    if t and t.get('status') == 'clocked_out':
        t['status'] = 'approved'
        save_db()
        flash('Timecard approved.')
    return redirect(url_for('timecards'))


@app.route('/timecards/<tid>/delete', methods=['POST'])
def timecard_delete(tid):
    if remove_from('timecards', tid):
        flash('Timecard deleted (moved to Recycle Bin).')
    return redirect(url_for('timecards'))


@app.route('/timecards/payroll')
def payroll():
    start = request.args.get('start') or (today() - timedelta(days=13)).isoformat()
    end = request.args.get('end') or today().isoformat()
    agg = {}
    for t in DB['timecards']:
        if not t.get('clock_out'):
            continue
        d = (t.get('clock_in') or '')[:10]
        if not (start <= d <= end):
            continue
        wid = t['worker_id']
        h = t.get('hours') or compute_hours(t.get('clock_in'), t.get('clock_out'))
        agg.setdefault(wid, {'hours': 0.0, 'records': 0})
        agg[wid]['hours'] += h
        agg[wid]['records'] += 1
    rows = []
    for wid, a in agg.items():
        w = find('workers', wid)
        rate = (w or {}).get('hourly_rate') or 0.0
        rows.append({'worker': worker_name(wid), 'trade': (w or {}).get('trade', '—'),
                     'rate': rate, 'hours': round(a['hours'], 2),
                     'records': a['records'],
                     'gross': round(a['hours'] * rate, 2)})
    rows.sort(key=lambda r: r['worker'])
    total_gross = round(sum(r['gross'] for r in rows), 2)
    total_hours = round(sum(r['hours'] for r in rows), 2)
    return render_template('payroll.html', rows=rows, start=start, end=end,
                           total_gross=total_gross, total_hours=total_hours)


# ================= INCIDENTS =================

@app.route('/incidents', methods=['GET', 'POST'])
def incidents():
    if request.method == 'POST':
        inc = {'id': new_id(), 'site_id': request.form.get('site_id'),
               'severity': request.form.get('severity', 'minor'),
               'status': 'open',
               'description': request.form.get('description', '').strip(),
               'photo_url': save_upload(request.files.get('photo')),
               'lat': _f(request.form.get('lat')), 'lng': _f(request.form.get('lng')),
               'created_at': now_iso()}
        DB['incidents'].append(inc)
        save_db()
        flash('Incident reported.')
        return redirect(url_for('incidents'))
    fsite = request.args.get('site') or 'all'
    rows = [i for i in DB['incidents'] if fsite == 'all' or i['site_id'] == fsite]
    rows.sort(key=lambda i: i.get('created_at', ''), reverse=True)
    return render_template('incidents.html', rows=rows, sites=DB['sites'], fsite=fsite)


@app.route('/incidents/<iid>/resolve', methods=['POST'])
def incident_resolve(iid):
    i = find('incidents', iid)
    if i:
        i['status'] = 'resolved'
        save_db()
        flash('Incident marked resolved.')
    return redirect(url_for('incidents'))


@app.route('/incidents/<iid>/delete', methods=['POST'])
def incident_delete(iid):
    if remove_from('incidents', iid):
        flash('Incident deleted (moved to Recycle Bin).')
    return redirect(url_for('incidents'))


# ================= DAILY LOGS =================

@app.route('/daily-logs', methods=['GET', 'POST'])
def daily_logs():
    if request.method == 'POST':
        DB['daily_logs'].append({
            'id': new_id(), 'site_id': request.form.get('site_id'),
            'log_date': request.form.get('log_date') or today().isoformat(),
            'weather': request.form.get('weather', '').strip(),
            'notes': request.form.get('notes', '').strip(),
            'delays': request.form.get('delays', '').strip(),
            'visitors': request.form.get('visitors', '').strip()})
        save_db()
        flash('Daily log saved.')
        return redirect(url_for('daily_logs'))
    fsite = request.args.get('site') or 'all'
    rows = [l for l in DB['daily_logs'] if fsite == 'all' or l['site_id'] == fsite]
    rows.sort(key=lambda l: l.get('log_date', ''), reverse=True)
    return render_template('daily_logs.html', rows=rows, sites=DB['sites'],
                           fsite=fsite, today=today().isoformat())


@app.route('/daily-logs/<lid>/delete', methods=['POST'])
def daily_log_delete(lid):
    if remove_from('daily_logs', lid):
        flash('Daily log deleted (moved to Recycle Bin).')
    return redirect(url_for('daily_logs'))


# ================= LABOUR =================

@app.route('/labour', methods=['GET', 'POST'])
def labour():
    if request.method == 'POST':
        DB['labour'].append({
            'id': new_id(), 'site_id': request.form.get('site_id'),
            'date': request.form.get('date') or today().isoformat(),
            'trade': request.form.get('trade', '').strip() or 'Other',
            'workers_count': int(request.form.get('workers_count') or 0),
            'hours': _f(request.form.get('hours')) or 0.0})
        save_db()
        flash('Labour entry logged.')
        return redirect(url_for('labour'))
    tdy = today().isoformat()
    td = [l for l in DB['labour'] if l.get('date') == tdy]
    stats = {'workers': sum(l.get('workers_count', 0) for l in td),
             'hours': round(sum(l.get('hours', 0) for l in td), 1),
             'trades': len({l.get('trade') for l in td})}
    by_date = {}
    for l in sorted(DB['labour'], key=lambda x: x.get('date', ''), reverse=True):
        by_date.setdefault(l.get('date'), []).append(l)
    return render_template('labour.html', stats=stats, by_date=by_date,
                           sites=DB['sites'], trades=TRADES, today=tdy)


@app.route('/labour/<lid>/delete', methods=['POST'])
def labour_delete(lid):
    if remove_from('labour', lid):
        flash('Labour entry deleted (moved to Recycle Bin).')
    return redirect(url_for('labour'))


# ================= MATERIALS =================

@app.route('/materials')
def materials():
    fsite = request.args.get('site') or 'all'
    rows = [{'m': m, 'low': is_low_stock(m)} for m in DB['materials']
            if fsite == 'all' or m['site_id'] == fsite]
    return render_template('materials.html', rows=rows, sites=DB['sites'], fsite=fsite)


@app.route('/materials/new', methods=['GET', 'POST'])
def material_new():
    if request.method == 'POST':
        m = {'id': new_id(), 'site_id': request.form.get('site_id'),
             'name': request.form.get('name', '').strip(),
             'quantity': _f(request.form.get('quantity')) or 0,
             'unit': request.form.get('unit', '').strip() or 'pcs',
             'reorder_threshold': _f(request.form.get('reorder_threshold')) or 0,
             'photo_url': save_upload(request.files.get('photo'))}
        DB['materials'].append(m)
        save_db()
        flash(f"Material '{m['name']}' added.")
        return redirect(url_for('materials'))
    return render_template('material_form.html', m=None, sites=DB['sites'])


@app.route('/materials/<mid>/edit', methods=['GET', 'POST'])
def material_edit(mid):
    m = find('materials', mid)
    if not m:
        abort(404)
    if request.method == 'POST':
        m['site_id'] = request.form.get('site_id')
        m['name'] = request.form.get('name', '').strip()
        m['quantity'] = _f(request.form.get('quantity')) or 0
        m['unit'] = request.form.get('unit', '').strip() or 'pcs'
        m['reorder_threshold'] = _f(request.form.get('reorder_threshold')) or 0
        ph = save_upload(request.files.get('photo'))
        if ph:
            m['photo_url'] = ph
        save_db()
        flash('Material updated.')
        return redirect(url_for('materials'))
    return render_template('material_form.html', m=m, sites=DB['sites'])


@app.route('/materials/<mid>/delete', methods=['POST'])
def material_delete(mid):
    if remove_from('materials', mid):
        flash('Material deleted (moved to Recycle Bin).')
    return redirect(url_for('materials'))


# ================= QA / QC =================

@app.route('/qa')
def qa():
    tab = request.args.get('tab') or 'defects'
    fsite = request.args.get('site') or 'all'
    defects = [d for d in DB['defects'] if fsite == 'all' or d['site_id'] == fsite]
    defects.sort(key=lambda d: d.get('created_at', ''), reverse=True)
    checks = [c for c in DB['qa_checks'] if fsite == 'all' or c['site_id'] == fsite]
    checks.sort(key=lambda c: c.get('check_date', ''), reverse=True)
    return render_template('qa.html', tab=tab, defects=defects, checks=checks,
                           sites=DB['sites'], fsite=fsite,
                           open_count=sum(1 for d in defects if d.get('status') == 'open'))


@app.route('/qa/defects/new', methods=['GET', 'POST'])
def defect_new():
    if request.method == 'POST':
        d = {'id': new_id(), 'site_id': request.form.get('site_id'),
             'category': request.form.get('category', '').strip() or 'General',
             'severity': request.form.get('severity', 'minor'),
             'status': 'open',
             'location': request.form.get('location', '').strip(),
             'description': request.form.get('description', '').strip(),
             'photo_url': save_upload(request.files.get('photo')),
             'assigned_to': request.form.get('assigned_to', '').strip(),
             'due_date': request.form.get('due_date', ''),
             'created_at': now_iso()}
        DB['defects'].append(d)
        save_db()
        flash('Defect logged.')
        return redirect(url_for('qa'))
    return render_template('defect_form.html', d=None, sites=DB['sites'],
                           workers=DB['workers'])


@app.route('/qa/defects/<did>/status', methods=['POST'])
def defect_status(did):
    d = find('defects', did)
    if d:
        d['status'] = request.form.get('status', 'open')
        save_db()
        flash('Defect status updated.')
    return redirect(url_for('qa'))


@app.route('/qa/defects/<did>/edit', methods=['GET', 'POST'])
def defect_edit(did):
    d = find('defects', did)
    if not d:
        abort(404)
    if request.method == 'POST':
        d['site_id'] = request.form.get('site_id')
        d['category'] = request.form.get('category', '').strip()
        d['severity'] = request.form.get('severity', 'minor')
        d['location'] = request.form.get('location', '').strip()
        d['description'] = request.form.get('description', '').strip()
        ph = save_upload(request.files.get('photo'))
        if ph:
            d['photo_url'] = ph
        d['assigned_to'] = request.form.get('assigned_to', '').strip()
        d['due_date'] = request.form.get('due_date', '')
        save_db()
        flash('Defect updated.')
        return redirect(url_for('qa'))
    return render_template('defect_form.html', d=d, sites=DB['sites'], workers=DB['workers'])


@app.route('/qa/defects/<did>/delete', methods=['POST'])
def defect_delete(did):
    if remove_from('defects', did):
        flash('Defect deleted (moved to Recycle Bin).')
    return redirect(url_for('qa'))


@app.route('/qa/checks/new', methods=['GET', 'POST'])
def check_new():
    if request.method == 'POST':
        c = {'id': new_id(), 'site_id': request.form.get('site_id'),
             'name': request.form.get('name', '').strip(),
             'location': request.form.get('location', '').strip(),
             'result': request.form.get('result', 'pass'),
             'status': 'awaiting_signoff',
             'inspector': request.form.get('inspector', '').strip(),
             'notes': request.form.get('notes', '').strip(),
             'check_date': request.form.get('check_date') or today().isoformat()}
        DB['qa_checks'].append(c)
        save_db()
        flash('QA check logged.')
        return redirect(url_for('qa', tab='checks'))
    return render_template('check_form.html', sites=DB['sites'])


@app.route('/qa/checks/<cid>/signoff', methods=['POST'])
def check_signoff(cid):
    c = find('qa_checks', cid)
    if c:
        c['status'] = 'signed_off'
        save_db()
        flash('Check signed off.')
    return redirect(url_for('qa', tab='checks'))


@app.route('/qa/checks/<cid>/delete', methods=['POST'])
def check_delete(cid):
    if remove_from('qa_checks', cid):
        flash('QA check deleted (moved to Recycle Bin).')
    return redirect(url_for('qa', tab='checks'))


# ================= DATA & RESTORE =================

@app.route('/data')
def data_page():
    trash = sorted(enumerate(DB['trash']),
                   key=lambda x: x[1].get('deleted_at', ''), reverse=True)
    snaps = sorted(DB['snapshots'], key=lambda s: s.get('created_at', ''), reverse=True)
    return render_template('data.html', trash=trash, snapshots=snaps)


@app.route('/data/backup')
def data_backup():
    save_db()
    return send_file(DB_PATH, mimetype='application/json', as_attachment=True,
                     download_name='site-manager-backup.json')


@app.route('/data/snapshot', methods=['POST'])
def data_snapshot():
    name = (request.form.get('name') or '').strip() or f"Snapshot {now_iso()}"
    snap_data = {k: copy.deepcopy(v) for k, v in DB.items() if k != 'snapshots'}
    DB['snapshots'].append({'id': new_id(), 'name': name,
                            'created_at': now_iso(), 'data': snap_data})
    save_db()
    flash(f"Snapshot '{name}' saved.")
    return redirect(url_for('data_page'))


@app.route('/data/snapshot/<sid>/restore', methods=['POST'])
def snapshot_restore(sid):
    s = find('snapshots', sid)
    if not s:
        abort(404)
    snap = s['data']
    for coll in COLLECTIONS:
        if coll == 'snapshots':
            continue
        if coll in snap:
            DB[coll] = copy.deepcopy(snap[coll])
    save_db()
    flash(f"Restored snapshot '{s['name']}'.")
    return redirect(url_for('data_page'))


@app.route('/data/snapshot/<sid>/delete', methods=['POST'])
def snapshot_delete(sid):
    DB['snapshots'] = [s for s in DB['snapshots'] if s.get('id') != sid]
    save_db()
    flash('Snapshot deleted.')
    return redirect(url_for('data_page'))


@app.route('/data/trash/<int:idx>/restore', methods=['POST'])
def trash_restore(idx):
    try:
        item = DB['trash'][idx]
    except IndexError:
        abort(404)
    coll, rec = item['type'], item['record']
    if coll in COLLECTIONS and not find(coll, rec.get('id')):
        DB[coll].append(rec)
    DB['trash'].pop(idx)
    save_db()
    flash('Record restored.')
    return redirect(url_for('data_page'))


@app.route('/data/trash/<int:idx>/delete', methods=['POST'])
def trash_delete(idx):
    try:
        DB['trash'].pop(idx)
    except IndexError:
        abort(404)
    save_db()
    flash('Record permanently deleted.')
    return redirect(url_for('data_page'))


@app.route('/data/trash/empty', methods=['POST'])
def trash_empty():
    DB['trash'] = []
    save_db()
    flash('Recycle bin emptied.')
    return redirect(url_for('data_page'))


# ================= ERROR / MAIN =================

@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', code=404, message='Page not found.'), 404


@app.errorhandler(410)
def gone(e):
    return render_template('error.html', code=410, message='This link has expired.'), 410


if __name__ == '__main__':
    import os
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))


# ================= WORKER / DISPATCH APIs (used by workers page JS) =================

@app.route('/api/workers/<wid>')
def api_worker(wid):
    w = find('workers', wid)
    if not w:
        abort(404)
    tcs = [t for t in DB['timecards'] if t['worker_id'] == wid]
    tcs.sort(key=lambda t: t.get('clock_in') or '', reverse=True)
    rows = []
    for t in tcs[:20]:
        rows.append({
            'date': (t.get('clock_in') or '')[:10],
            'in': fmt_dt(t.get('clock_in')),
            'out': fmt_dt(t.get('clock_out')) if t.get('clock_out') else 'Still on shift',
            'status': t.get('status'),
            'hours': t.get('hours') or compute_hours(t.get('clock_in'), t.get('clock_out')),
        })
    return jsonify({'worker': w, 'timecards': rows,
                    'counts': {'timecards': len(tcs),
                               'hours': round(sum(r['hours'] for r in rows), 1)}})


@app.route('/api/dispatches')
def api_dispatches():
    out = []
    for d in sorted(DB['dispatches'], key=lambda x: x.get('created_at', ''), reverse=True)[:20]:
        out.append({'worker': worker_name(d.get('worker_id')),
                    'message': d.get('message'), 'at': fmt_dt(d.get('created_at'))})
    return jsonify(out)
