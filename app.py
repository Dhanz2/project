from flask import Flask, render_template, jsonify, request
from datetime import datetime
from pathlib import Path
from werkzeug.utils import secure_filename
import sqlite3
import uuid
import os
import secrets

from ai.video_detector import process_video

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
# Set APP_DATA_DIR to a persistent mounted volume when deploying to a host.
DATA_DIR = Path(os.environ.get("APP_DATA_DIR", BASE_DIR / "instance"))
DB = DATA_DIR / "campus.db"
UPLOAD_DIR = DATA_DIR / "uploads"
PROCESSED_DIR = DATA_DIR / "processed"
EVIDENCE_DIR = DATA_DIR / "evidence"
DATA_DIR.mkdir(parents=True, exist_ok=True)
for p in (UPLOAD_DIR, PROCESSED_DIR, EVIDENCE_DIR): p.mkdir(parents=True, exist_ok=True)
ALLOWED_VIDEO = {".mp4", ".avi", ".mov", ".mkv", ".webm"}

@app.before_request
def require_dashboard_password():
    password = os.environ.get("SAFETY_ADMIN_PASSWORD")
    if not password or request.endpoint == "health":
        return None
    auth = request.authorization
    if auth and auth.username == "admin" and secrets.compare_digest(auth.password or "", password):
        return None
    return ("Authentication required", 401, {"WWW-Authenticate": 'Basic realm="Campus Traffic Safety"'})

def init_db():
    con=sqlite3.connect(DB); cur=con.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS incidents (
      id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL, location TEXT NOT NULL,
      category TEXT NOT NULL, description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Pending Review',
      vehicle_type TEXT, track_id INTEGER, direction TEXT, evidence_url TEXT, video_url TEXT)''')
    cols={r[1] for r in cur.execute('PRAGMA table_info(incidents)').fetchall()}
    for name,typ in [("vehicle_type","TEXT"),("track_id","INTEGER"),("direction","TEXT"),("evidence_url","TEXT"),("video_url","TEXT")]:
        if name not in cols: cur.execute(f'ALTER TABLE incidents ADD COLUMN {name} {typ}')
    con.commit(); con.close()

def add_incident(location, category, description, **extra):
    con=sqlite3.connect(DB); cur=con.cursor()
    cur.execute('''INSERT INTO incidents(time,location,category,description,status,vehicle_type,track_id,direction,evidence_url,video_url)
                   VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),location,category,description,'Pending Review',
                 extra.get('vehicle_type'),extra.get('track_id'),extra.get('direction'),extra.get('evidence_url'),extra.get('video_url')))
    con.commit(); iid=cur.lastrowid; con.close(); return iid

@app.route('/')
def index(): return render_template('index.html')

@app.get('/api/incidents')
def incidents():
    con=sqlite3.connect(DB); con.row_factory=sqlite3.Row
    rows=con.execute('SELECT * FROM incidents ORDER BY id DESC').fetchall(); con.close()
    return jsonify([dict(r) for r in rows])

@app.get('/api/stats')
def stats():
    con=sqlite3.connect(DB)
    d={'total':con.execute('SELECT COUNT(*) FROM incidents').fetchone()[0],
       'pending':con.execute("SELECT COUNT(*) FROM incidents WHERE status='Pending Review'").fetchone()[0],
       'traffic':con.execute("SELECT COUNT(*) FROM incidents WHERE category='Traffic'").fetchone()[0],
       'reviewed':con.execute("SELECT COUNT(*) FROM incidents WHERE status IN ('Verified','Resolved')").fetchone()[0]}
    con.close(); return jsonify(d)

@app.get('/api/health')
def health():
    return jsonify({'status': 'ok'})

@app.patch('/api/incidents/<int:incident_id>')
def update_incident(incident_id):
    status=request.get_json(force=True).get('status'); allowed={'Pending Review','Verified','Dismissed','Resolved'}
    if status not in allowed: return jsonify({'error':'Invalid status'}),400
    con=sqlite3.connect(DB); cur=con.cursor(); cur.execute('UPDATE incidents SET status=? WHERE id=?',(status,incident_id)); con.commit(); changed=cur.rowcount; con.close()
    return (jsonify({'message':'Updated'}) if changed else (jsonify({'error':'Incident not found'}),404))

@app.post('/api/analyze-video')
def analyze_video():
    video=request.files.get('video'); location=request.form.get('location','Main Gate').strip() or 'Main Gate'
    expected=request.form.get('expected_direction','outbound')
    if expected not in {'inbound','outbound'}: expected='outbound'
    if not video or not video.filename: return jsonify({'error':'Please choose a video file.'}),400
    suffix=Path(video.filename).suffix.lower()
    if suffix not in ALLOWED_VIDEO: return jsonify({'error':'Unsupported video type. Use MP4, AVI, MOV, MKV or WEBM.'}),400
    job=uuid.uuid4().hex[:10]; input_path=UPLOAD_DIR/f'{job}_{secure_filename(video.filename)}'
    output_path=PROCESSED_DIR/f'{job}_annotated.mp4'; video.save(input_path)
    try:
        result=process_video(str(input_path),str(output_path),expected_direction=expected,evidence_dir=str(EVIDENCE_DIR),job_id=job)
        video_url=f'/media/processed/{output_path.name}'
        for a in result['alerts']:
            add_incident(location,'Traffic',a['description']+' Human verification required.',
                         vehicle_type=a['vehicle'],track_id=a['track_id'],direction=a['direction'],
                         evidence_url=a['evidence_url'],video_url=video_url)
        return jsonify({'message':'Video analysis complete','video_url':video_url,'video_download':video_url,
                        'frames':result['frames'],'unique_vehicles':result['unique_vehicles'],
                        'vehicle_counts':result['vehicle_counts'],'alerts':result['alerts']})
    except Exception as exc:
        app.logger.exception("Video analysis failed")
        return jsonify({'error':f'Video analysis failed: {exc}'}),500
    finally:
        input_path.unlink(missing_ok=True)

@app.get('/media/<kind>/<path:filename>')
def media(kind, filename):
    from flask import send_from_directory, abort
    folders = {'processed': PROCESSED_DIR, 'evidence': EVIDENCE_DIR}
    if kind not in folders:
        abort(404)
    return send_from_directory(folders[kind], filename)


init_db()
if __name__=='__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

