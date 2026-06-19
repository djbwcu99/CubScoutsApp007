#!/usr/bin/env python3
"""
Cub Scouts Pack Manager - Python/Flask Backend
Supports both SQLite (local dev) and PostgreSQL (Railway/production)
Run locally:  bash start.sh  →  http://localhost:3000
Default admin password: cubmaster123
"""

import os, sys, json, csv, io, hashlib, hmac, secrets
from datetime import datetime, date
from functools import wraps
from flask import Flask, request, jsonify, session, send_from_directory, Response, send_file

# ─── Try to import bcrypt, fall back to hashlib ─────────────
try:
    import bcrypt as _bcrypt
    def hash_password(pw): return _bcrypt.hashpw(pw.encode(), _bcrypt.gensalt()).decode()
    def check_password(pw, hsh): return _bcrypt.checkpw(pw.encode(), hsh.encode())
except ImportError:
    def hash_password(pw):
        salt = secrets.token_hex(16)
        h = hashlib.sha256((salt + pw).encode()).hexdigest()
        return f"{salt}:{h}"
    def check_password(pw, hsh):
        parts = hsh.split(':')
        if len(parts) != 2: return False
        salt, stored = parts
        return hashlib.sha256((salt + pw).encode()).hexdigest() == stored

# ─── Try to import reportlab for PDF ───────────────────────
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

app = Flask(__name__, static_folder='public', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
PORT = int(os.environ.get('PORT', 3000))

# ─── Database Layer ───────────────────────────────────────────
# Uses PostgreSQL when DATABASE_URL is set (Railway), otherwise SQLite (local dev)

DATABASE_URL = os.environ.get('DATABASE_URL', '')
DB_PATH = os.environ.get('DB_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scouts.db'))

class Database:
    """
    Unified SQLite / PostgreSQL interface.
    All fetch methods return plain Python dicts (never DB row objects).
    execute() returns the new row's id for INSERTs, None otherwise.
    """

    def __init__(self):
        self.is_pg = bool(DATABASE_URL)
        if self.is_pg:
            try:
                import psycopg2
                import psycopg2.extras
                import psycopg2.errorcodes
                self._pg = psycopg2
                self._DictCursor = psycopg2.extras.RealDictCursor
                self.IntegrityError = psycopg2.IntegrityError
            except ImportError:
                print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
                sys.exit(1)
        else:
            import sqlite3
            self._sqlite3 = sqlite3
            self.IntegrityError = sqlite3.IntegrityError

    def _conn(self):
        if self.is_pg:
            url = DATABASE_URL
            # Railway sometimes gives postgres:// — psycopg2 needs postgresql://
            if url.startswith('postgres://'):
                url = 'postgresql://' + url[len('postgres://'):]
            return self._pg.connect(url)
        else:
            conn = self._sqlite3.connect(DB_PATH)
            conn.row_factory = self._sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            return conn

    def _adapt(self, sql):
        """Convert SQLite SQL to PostgreSQL SQL where needed."""
        if not self.is_pg:
            return sql
        return (sql
            .replace('?', '%s')
            .replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'BIGSERIAL PRIMARY KEY')
            .replace("DEFAULT (datetime('now'))", 'DEFAULT NOW()')
            .replace("datetime('now')", 'NOW()')
        )

    def fetchone(self, sql, params=()):
        """Return one row as a dict, or None."""
        sql = self._adapt(sql)
        conn = self._conn()
        try:
            if self.is_pg:
                with conn.cursor(cursor_factory=self._DictCursor) as cur:
                    cur.execute(sql, params or None)
                    row = cur.fetchone()
                    return dict(row) if row else None
            else:
                with conn:
                    row = conn.execute(sql, params).fetchone()
                    return dict(row) if row else None
        finally:
            conn.close()

    def fetchall(self, sql, params=()):
        """Return all rows as a list of dicts."""
        sql = self._adapt(sql)
        conn = self._conn()
        try:
            if self.is_pg:
                with conn.cursor(cursor_factory=self._DictCursor) as cur:
                    cur.execute(sql, params or None)
                    return [dict(r) for r in cur.fetchall()]
            else:
                with conn:
                    return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    def execute(self, sql, params=(), returning_id=True):
        """
        Execute a statement.
        For INSERT statements: returns the new row's integer id (if returning_id=True).
        For UPDATE/DELETE: returns None.
        Pass returning_id=False for tables that don't have an 'id' column (e.g. settings).
        """
        sql = self._adapt(sql)
        conn = self._conn()
        try:
            if self.is_pg:
                is_insert = sql.strip().upper().startswith('INSERT')
                want_returning = is_insert and returning_id and 'RETURNING' not in sql.upper() and 'DO NOTHING' not in sql.upper()
                if want_returning:
                    sql += ' RETURNING id'
                with conn.cursor(cursor_factory=self._DictCursor) as cur:
                    cur.execute(sql, params or None)
                    conn.commit()
                    if want_returning and 'RETURNING' in sql.upper():
                        row = cur.fetchone()
                        return row['id'] if row else None
                    return None
            else:
                with conn:
                    cur = conn.execute(sql, params)
                    return cur.lastrowid
        finally:
            conn.close()

    def execute_script(self, statements):
        """Execute a list of SQL statements as a batch (used for schema creation)."""
        conn = self._conn()
        try:
            if self.is_pg:
                with conn.cursor() as cur:
                    for stmt in statements:
                        stmt = self._adapt(stmt.strip())
                        if stmt:
                            cur.execute(stmt)
                conn.commit()
            else:
                with conn:
                    conn.executescript('\n'.join(statements))
        finally:
            conn.close()

    def scalar(self, sql, params=()):
        """Return a single scalar value (first column of first row)."""
        sql = self._adapt(sql)
        conn = self._conn()
        try:
            if self.is_pg:
                with conn.cursor() as cur:
                    cur.execute(sql, params or None)
                    row = cur.fetchone()
                    return row[0] if row else None
            else:
                with conn:
                    row = conn.execute(sql, params).fetchone()
                    return row[0] if row else None
        finally:
            conn.close()


db = Database()


# ─── Schema ───────────────────────────────────────────────────
SQLITE_SCHEMA = ["""
    CREATE TABLE IF NOT EXISTS scouts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        firstName TEXT NOT NULL, lastName TEXT NOT NULL,
        rank TEXT NOT NULL, den TEXT, grade TEXT, dateJoined TEXT,
        parentName TEXT, parentEmail TEXT, parentPhone TEXT, notes TEXT,
        createdAt TEXT DEFAULT (datetime('now'))
    )""", """
    CREATE TABLE IF NOT EXISTS awards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scoutId INTEGER NOT NULL, name TEXT NOT NULL, type TEXT NOT NULL,
        status TEXT DEFAULT 'not_started', progress INTEGER DEFAULT 0,
        dateEarned TEXT, notes TEXT,
        createdAt TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (scoutId) REFERENCES scouts(id) ON DELETE CASCADE
    )""", """
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL, date TEXT NOT NULL,
        time TEXT, location TEXT, description TEXT, maxSignups INTEGER DEFAULT NULL,
        createdAt TEXT DEFAULT (datetime('now'))
    )""", """
    CREATE TABLE IF NOT EXISTS signups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scoutId INTEGER NOT NULL, eventId INTEGER NOT NULL,
        signupDate TEXT DEFAULT (datetime('now')), notes TEXT,
        FOREIGN KEY (scoutId) REFERENCES scouts(id) ON DELETE CASCADE,
        FOREIGN KEY (eventId) REFERENCES events(id) ON DELETE CASCADE,
        UNIQUE(scoutId, eventId)
    )""", """
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)
""", """
    CREATE TABLE IF NOT EXISTS event_slots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        eventId INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        capacity INTEGER,
        sortOrder INTEGER DEFAULT 0,
        createdAt TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (eventId) REFERENCES events(id) ON DELETE CASCADE
    )""", """
    CREATE TABLE IF NOT EXISTS slot_signups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slotId INTEGER NOT NULL,
        name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        notes TEXT,
        signupDate TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (slotId) REFERENCES event_slots(id) ON DELETE CASCADE
    )""", """
    CREATE TABLE IF NOT EXISTS award_requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        awardId INTEGER NOT NULL,
        text TEXT NOT NULL,
        completed INTEGER DEFAULT 0,
        sortOrder INTEGER DEFAULT 0,
        FOREIGN KEY (awardId) REFERENCES awards(id) ON DELETE CASCADE
    )
"""]

POSTGRES_SCHEMA = ["""
    CREATE TABLE IF NOT EXISTS scouts (
        id BIGSERIAL PRIMARY KEY,
        firstName TEXT NOT NULL, lastName TEXT NOT NULL,
        rank TEXT NOT NULL, den TEXT, grade TEXT, dateJoined TEXT,
        parentName TEXT, parentEmail TEXT, parentPhone TEXT, notes TEXT,
        createdAt TIMESTAMP DEFAULT NOW()
    )""", """
    CREATE TABLE IF NOT EXISTS awards (
        id BIGSERIAL PRIMARY KEY,
        scoutId BIGINT NOT NULL REFERENCES scouts(id) ON DELETE CASCADE,
        name TEXT NOT NULL, type TEXT NOT NULL,
        status TEXT DEFAULT 'not_started', progress INTEGER DEFAULT 0,
        dateEarned TEXT, notes TEXT,
        createdAt TIMESTAMP DEFAULT NOW()
    )""", """
    CREATE TABLE IF NOT EXISTS events (
        id BIGSERIAL PRIMARY KEY,
        title TEXT NOT NULL, date TEXT NOT NULL,
        time TEXT, location TEXT, description TEXT, maxSignups INTEGER,
        createdAt TIMESTAMP DEFAULT NOW()
    )""", """
    CREATE TABLE IF NOT EXISTS signups (
        id BIGSERIAL PRIMARY KEY,
        scoutId BIGINT NOT NULL REFERENCES scouts(id) ON DELETE CASCADE,
        eventId BIGINT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
        signupDate TIMESTAMP DEFAULT NOW(), notes TEXT,
        UNIQUE(scoutId, eventId)
    )""", """
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)
""", """
    CREATE TABLE IF NOT EXISTS event_slots (
        id BIGSERIAL PRIMARY KEY,
        eventId BIGINT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        description TEXT,
        capacity INTEGER,
        sortOrder INTEGER DEFAULT 0,
        createdAt TIMESTAMP DEFAULT NOW()
    )""", """
    CREATE TABLE IF NOT EXISTS slot_signups (
        id BIGSERIAL PRIMARY KEY,
        slotId BIGINT NOT NULL REFERENCES event_slots(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        notes TEXT,
        signupDate TIMESTAMP DEFAULT NOW()
    )""", """
    CREATE TABLE IF NOT EXISTS award_requirements (
        id BIGSERIAL PRIMARY KEY,
        awardId BIGINT NOT NULL REFERENCES awards(id) ON DELETE CASCADE,
        text TEXT NOT NULL,
        completed INTEGER DEFAULT 0,
        sortOrder INTEGER DEFAULT 0
    )
"""]


def init_db():
    schema = POSTGRES_SCHEMA if db.is_pg else SQLITE_SCHEMA
    db.execute_script(schema)

    # Set default admin password if not configured yet
    existing = db.fetchone("SELECT value FROM settings WHERE key='admin_password'")
    if not existing:
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ('admin_password', hash_password('cubmaster123')), returning_id=False)

    # Seed sample data if the scouts table is empty
    count = db.scalar("SELECT COUNT(*) FROM scouts")
    if count == 0:
        seed_data()


def seed_data():
    print("🌱 Seeding sample data...")
    from datetime import timedelta
    today = date.today()
    def offset(n): return str(today + timedelta(days=n))

    scouts_list = [
        ('Liam','Johnson','Lion','Den 1','Kindergarten','2024-09-01','Mark Johnson','mark.j@email.com','555-1001'),
        ('Emma','Williams','Tiger','Den 2','1st Grade','2024-09-01','Sarah Williams','sarah.w@email.com','555-1002'),
        ('Noah','Brown','Tiger','Den 2','1st Grade','2024-09-01','Chris Brown','chris.b@email.com','555-1003'),
        ('Olivia','Davis','Wolf','Den 3','2nd Grade','2023-09-01','Amy Davis','amy.d@email.com','555-1004'),
        ('Ethan','Martinez','Wolf','Den 3','2nd Grade','2023-09-01','Carlos Martinez','carlos.m@email.com','555-1005'),
        ('Ava','Taylor','Bear','Den 4','3rd Grade','2022-09-01','James Taylor','james.t@email.com','555-1006'),
        ('Mason','Anderson','Bear','Den 4','3rd Grade','2022-09-01','Lisa Anderson','lisa.a@email.com','555-1007'),
        ('Sophia','Thomas','Webelos','Den 5','4th Grade','2021-09-01','David Thomas','david.t@email.com','555-1008'),
        ('Lucas','Jackson','AOL','Den 6','5th Grade','2020-09-01','Karen Jackson','karen.j@email.com','555-1009'),
        ('Isabella','White','AOL','Den 6','5th Grade','2020-09-01','Tom White','tom.w@email.com','555-1010'),
    ]
    ids = []
    for s in scouts_list:
        new_id = db.execute(
            "INSERT INTO scouts (firstName,lastName,rank,den,grade,dateJoined,parentName,parentEmail,parentPhone) VALUES (?,?,?,?,?,?,?,?,?)", s)
        ids.append(new_id)
    s1,s2,s3,s4,s5,s6,s7,s8,s9,s10 = ids

    awards_list = [
        (s1,'Lion Badge','rank_badge','in_progress',60,None),
        (s1,'Animal Kingdom Adventure','required_adventure','completed',100,'2024-11-15'),
        (s1,'Big Cats','elective_adventure','in_progress',40,None),
        (s1,'Gizmos and Gadgets','elective_adventure','not_started',0,None),
        (s2,'Tiger Badge','rank_badge','in_progress',75,None),
        (s2,'Tiger Bites','required_adventure','completed',100,'2024-12-01'),
        (s2,'Earn Your Stripes','elective_adventure','in_progress',50,None),
        (s2,"Movin' On",'elective_adventure','completed',100,'2025-01-20'),
        (s3,'Tiger Badge','rank_badge','in_progress',30,None),
        (s3,'Tiger Bites','required_adventure','in_progress',60,None),
        (s4,'Wolf Badge','rank_badge','completed',100,'2024-05-10'),
        (s4,'Call of the Wild','required_adventure','completed',100,'2024-03-12'),
        (s4,'Paws on the Path','required_adventure','completed',100,'2024-04-01'),
        (s4,'Code of the Wolf','elective_adventure','completed',100,'2024-04-20'),
        (s4,'Finding Your Way','elective_adventure','in_progress',80,None),
        (s5,'Wolf Badge','rank_badge','in_progress',55,None),
        (s5,'Call of the Wild','required_adventure','completed',100,'2024-06-01'),
        (s5,'Howling at the Moon','required_adventure','in_progress',70,None),
        (s6,'Bear Badge','rank_badge','completed',100,'2024-05-15'),
        (s6,'Bear Claws','required_adventure','completed',100,'2024-02-28'),
        (s6,'Bear Necessities','required_adventure','completed',100,'2024-03-15'),
        (s6,'Baloo the Builder','elective_adventure','completed',100,'2024-04-10'),
        (s6,'Super Science','elective_adventure','in_progress',90,None),
        (s7,'Bear Badge','rank_badge','in_progress',45,None),
        (s7,'Bear Claws','required_adventure','in_progress',60,None),
        (s7,'Robotics','elective_adventure','in_progress',30,None),
        (s8,'Webelos Badge','rank_badge','in_progress',85,None),
        (s8,'Stronger, Faster, Higher','required_adventure','completed',100,'2024-11-01'),
        (s8,'First Responder','required_adventure','completed',100,'2024-10-15'),
        (s8,'Engineer','elective_adventure','in_progress',70,None),
        (s8,'Game Design','elective_adventure','completed',100,'2025-01-05'),
        (s9,'Arrow of Light Badge','rank_badge','in_progress',90,None),
        (s9,'Building a Better World','required_adventure','completed',100,'2025-01-10'),
        (s9,'Scouting Adventure','required_adventure','completed',100,'2025-01-20'),
        (s9,'Camper','elective_adventure','completed',100,'2024-12-05'),
        (s9,'First Aid','elective_adventure','in_progress',50,None),
        (s10,'Arrow of Light Badge','rank_badge','completed',100,'2025-02-01'),
        (s10,'Building a Better World','required_adventure','completed',100,'2024-11-30'),
        (s10,'Duty to God and Country','required_adventure','completed',100,'2024-12-15'),
        (s10,'Scouting Adventure','required_adventure','completed',100,'2025-01-10'),
        (s10,'Cyclist','elective_adventure','completed',100,'2025-01-25'),
    ]
    for a in awards_list:
        db.execute("INSERT INTO awards (scoutId,name,type,status,progress,dateEarned) VALUES (?,?,?,?,?,?)", a)

    events_list = [
        ('Pack Meeting - April', offset(5), '6:30 PM', 'Community Center, Rm 101', 'Monthly pack meeting. All scouts and families welcome.'),
        ('Pinewood Derby', offset(12), '10:00 AM', 'Main Gymnasium', 'Annual Pinewood Derby race! Car check-in starts at 9 AM.'),
        ('Camping Trip', offset(18), '8:00 AM', 'Eagle Creek Campground', 'Two-night camping trip. Bring full gear.'),
        ('Service Project - Park Cleanup', offset(25), '9:00 AM', 'Riverside Park', 'Community service — pack gloves and work clothes.'),
        ('Blue & Gold Banquet', offset(35), '5:00 PM', 'Elk Lodge Hall', "Annual Blue & Gold Banquet celebrating Scouting's anniversary."),
        ('STEM Day', offset(-5), '1:00 PM', 'Public Library', 'Fun STEM activities with experiments and robotics.'),
    ]
    event_ids = []
    for e in events_list:
        new_id = db.execute("INSERT INTO events (title,date,time,location,description) VALUES (?,?,?,?,?)", e)
        event_ids.append(new_id)
    e1,e2,e3,e4,e5,e6 = event_ids

    # Insert signups — ON CONFLICT DO NOTHING handles duplicates for both DBs
    signup_pairs = [
        (s1,e1),(s2,e1),(s3,e1),(s4,e1),(s5,e1),(s6,e1),(s7,e1),(s8,e1),(s9,e1),
        (s2,e2),(s4,e2),(s6,e2),(s8,e2),(s9,e2),
        (s1,e3),(s3,e3),(s5,e3),(s7,e3),
        (s9,e4),(s10,e4),(s8,e4),
        (s2,e6),(s4,e6),(s8,e6),(s10,e6),
    ]
    for su in signup_pairs:
        try:
            if db.is_pg:
                db.execute("INSERT INTO signups (scoutId,eventId) VALUES (?,?) ON CONFLICT (scoutId,eventId) DO NOTHING", su)
            else:
                db.execute("INSERT OR IGNORE INTO signups (scoutId,eventId) VALUES (?,?)", su)
        except Exception:
            pass

    print("✅ Sample data seeded!")


DEFAULT_AWARDS = {
    'Lion': [
        ('Lion Badge','rank_badge'),('Animal Kingdom Adventure','required_adventure'),
        ('Big Cats','elective_adventure'),('Curiosity, Intrigue, and Magical Mysteries','elective_adventure'),
        ('Gizmos and Gadgets','elective_adventure'),('Happy Hunting','elective_adventure'),
        ('Let It Grow','elective_adventure'),('Make It Move','elective_adventure'),
        ("My Family's Duty to God",'elective_adventure'),('Rumble in the Jungle','elective_adventure'),
    ],
    'Tiger': [
        ('Tiger Badge','rank_badge'),('Tiger Bites','required_adventure'),
        ('Built by Baden-Powell','elective_adventure'),('Curiosity, Intrigue, and Magical Mysteries','elective_adventure'),
        ('Earn Your Stripes','elective_adventure'),('Gizmos and Gadgets','elective_adventure'),
        ("Movin' On",'elective_adventure'),("My Family's Duty to God",'elective_adventure'),
        ('Sky is the Limit','elective_adventure'),('Tiger-iffic','elective_adventure'),
        ('Tigers in the Wild','elective_adventure'),
    ],
    'Wolf': [
        ('Wolf Badge','rank_badge'),('Call of the Wild','required_adventure'),
        ('Duty to God Footsteps','required_adventure'),('Howling at the Moon','required_adventure'),
        ('Paws on the Path','required_adventure'),('Running with the Pack','required_adventure'),
        ('Adventures in Coins','elective_adventure'),('Air of the Wolf','elective_adventure'),
        ('Code of the Wolf','elective_adventure'),('Cubs who Care','elective_adventure'),
        ('Digging in the Past','elective_adventure'),('Finding Your Way','elective_adventure'),
        ('Paws of Skill','elective_adventure'),('Spirit of the Water','elective_adventure'),
    ],
    'Bear': [
        ('Bear Badge','rank_badge'),('Bear Claws','required_adventure'),
        ('Bear Necessities','required_adventure'),('Fellowship and Duty to God','required_adventure'),
        ('Fur, Feathers, and Ferns','required_adventure'),('Baloo the Builder','elective_adventure'),
        ('Beat of the Drum','elective_adventure'),('A Bear Goes Fishing','elective_adventure'),
        ('Forensics','elective_adventure'),('Grin and Bear It','elective_adventure'),
        ('Make It Move','elective_adventure'),('Robotics','elective_adventure'),('Super Science','elective_adventure'),
    ],
    'Webelos': [
        ('Webelos Badge','rank_badge'),('Duty to God and You','required_adventure'),
        ('First Responder','required_adventure'),('Stronger, Faster, Higher','required_adventure'),
        ('Into the Wild','required_adventure'),('Into the Woods','required_adventure'),
        ('Build My Own Hero','elective_adventure'),('Earth Rocks','elective_adventure'),
        ('Engineer','elective_adventure'),('Fix It','elective_adventure'),
        ('Game Design','elective_adventure'),('Maestro!','elective_adventure'),
        ('Webelos Walkabout','elective_adventure'),
    ],
    'AOL': [
        ('Arrow of Light Badge','rank_badge'),('Building a Better World','required_adventure'),
        ('Duty to God and Country','required_adventure'),('Scouting Adventure','required_adventure'),
        ('Camper','elective_adventure'),('Cyclist','elective_adventure'),('First Aid','elective_adventure'),
        ('Fishing','elective_adventure'),('Floater','elective_adventure'),
        ('Into the Wild','elective_adventure'),('Into the Woods','elective_adventure'),
        ('Outdoor Adventurer','elective_adventure'),('Paddle Craft','elective_adventure'),
    ],
}

# ─── Auth Helpers ────────────────────────────────────────────
def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            return jsonify({'error': 'Unauthorized — admin access required'}), 401
        return f(*args, **kwargs)
    return decorated

# ─── Auth Routes ─────────────────────────────────────────────
@app.route('/api/auth/status')
def auth_status():
    return jsonify({'isAdmin': bool(session.get('is_admin'))})

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    data = request.json or {}
    password = data.get('password', '')
    row = db.fetchone("SELECT value FROM settings WHERE key='admin_password'")
    if not row:
        return jsonify({'error': 'No admin password configured'}), 500
    if check_password(password, row['value']):
        session['is_admin'] = True
        return jsonify({'success': True})
    return jsonify({'error': 'Incorrect password'}), 401

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/auth/password', methods=['PUT'])
@require_admin
def auth_change_password():
    data = request.json or {}
    new_pw = data.get('newPassword', '')
    if len(new_pw) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    db.execute("UPDATE settings SET value=? WHERE key='admin_password'", (hash_password(new_pw),))
    return jsonify({'success': True})

# ─── Scout Routes ────────────────────────────────────────────
@app.route('/api/scouts', methods=['GET'])
def get_scouts():
    rows = db.fetchall("SELECT * FROM scouts ORDER BY rank, lastName, firstName")
    return jsonify(rows)

@app.route('/api/scouts/<int:scout_id>', methods=['GET'])
def get_scout(scout_id):
    row = db.fetchone("SELECT * FROM scouts WHERE id=?", (scout_id,))
    if not row:
        return jsonify({'error': 'Scout not found'}), 404
    return jsonify(row)

@app.route('/api/scouts', methods=['POST'])
@require_admin
def create_scout():
    d = request.json or {}
    if not d.get('firstName') or not d.get('lastName') or not d.get('rank'):
        return jsonify({'error': 'firstName, lastName, and rank are required'}), 400
    new_id = db.execute(
        "INSERT INTO scouts (firstName,lastName,rank,den,grade,dateJoined,parentName,parentEmail,parentPhone,notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (d['firstName'],d['lastName'],d['rank'],d.get('den'),d.get('grade'),d.get('dateJoined'),
         d.get('parentName'),d.get('parentEmail'),d.get('parentPhone'),d.get('notes'))
    )
    row = db.fetchone("SELECT * FROM scouts WHERE id=?", (new_id,))
    return jsonify(row), 201

@app.route('/api/scouts/<int:scout_id>', methods=['PUT'])
@require_admin
def update_scout(scout_id):
    d = request.json or {}
    existing = db.fetchone("SELECT id FROM scouts WHERE id=?", (scout_id,))
    if not existing:
        return jsonify({'error': 'Scout not found'}), 404
    db.execute(
        "UPDATE scouts SET firstName=?,lastName=?,rank=?,den=?,grade=?,dateJoined=?,parentName=?,parentEmail=?,parentPhone=?,notes=? WHERE id=?",
        (d.get('firstName'),d.get('lastName'),d.get('rank'),d.get('den'),d.get('grade'),
         d.get('dateJoined'),d.get('parentName'),d.get('parentEmail'),d.get('parentPhone'),
         d.get('notes'),scout_id)
    )
    row = db.fetchone("SELECT * FROM scouts WHERE id=?", (scout_id,))
    return jsonify(row)

@app.route('/api/scouts/<int:scout_id>', methods=['DELETE'])
@require_admin
def delete_scout(scout_id):
    db.execute("DELETE FROM scouts WHERE id=?", (scout_id,))
    return jsonify({'success': True})

# ─── Award Routes ────────────────────────────────────────────
@app.route('/api/awards', methods=['GET'])
def get_awards():
    scout_id = request.args.get('scoutId')
    if scout_id:
        rows = db.fetchall("SELECT * FROM awards WHERE scoutId=? ORDER BY type, name", (scout_id,))
    else:
        rows = db.fetchall("SELECT * FROM awards ORDER BY scoutId, type, name")
    return jsonify(rows)

@app.route('/api/awards/defaults/<rank>', methods=['GET'])
def get_default_awards(rank):
    return jsonify([{'name': n, 'type': t} for n, t in DEFAULT_AWARDS.get(rank, [])])

@app.route('/api/awards', methods=['POST'])
@require_admin
def create_award():
    d = request.json or {}
    if not d.get('scoutId') or not d.get('name') or not d.get('type'):
        return jsonify({'error': 'scoutId, name, and type are required'}), 400
    new_id = db.execute(
        "INSERT INTO awards (scoutId,name,type,status,progress,dateEarned,notes) VALUES (?,?,?,?,?,?,?)",
        (d['scoutId'],d['name'],d['type'],d.get('status','not_started'),d.get('progress',0),d.get('dateEarned'),d.get('notes'))
    )
    row = db.fetchone("SELECT * FROM awards WHERE id=?", (new_id,))
    return jsonify(row), 201

@app.route('/api/awards/<int:award_id>', methods=['PUT'])
@require_admin
def update_award(award_id):
    d = request.json or {}
    db.execute(
        "UPDATE awards SET name=?,type=?,status=?,progress=?,dateEarned=?,notes=? WHERE id=?",
        (d.get('name'),d.get('type'),d.get('status'),d.get('progress'),d.get('dateEarned'),d.get('notes'),award_id)
    )
    row = db.fetchone("SELECT * FROM awards WHERE id=?", (award_id,))
    return jsonify(row)

@app.route('/api/awards/<int:award_id>', methods=['DELETE'])
@require_admin
def delete_award(award_id):
    db.execute("DELETE FROM awards WHERE id=?", (award_id,))
    return jsonify({'success': True})

@app.route('/api/awards/bulk', methods=['POST'])
@require_admin
def bulk_awards():
    d = request.json or {}
    scout_id = d.get('scoutId')
    scout = db.fetchone("SELECT * FROM scouts WHERE id=?", (scout_id,))
    if not scout:
        return jsonify({'error': 'Scout not found'}), 404
    rank = d.get('rank') or scout['rank']
    for name, atype in DEFAULT_AWARDS.get(rank, []):
        # Check if already exists before inserting (avoids duplicates)
        exists = db.fetchone("SELECT id FROM awards WHERE scoutId=? AND name=?", (scout_id, name))
        if not exists:
            db.execute("INSERT INTO awards (scoutId,name,type,status,progress) VALUES (?,?,?,?,?)",
                       (scout_id, name, atype, 'not_started', 0))
    rows = db.fetchall("SELECT * FROM awards WHERE scoutId=? ORDER BY type, name", (scout_id,))
    return jsonify(rows)

# ─── Award Requirement Routes ─────────────────────────────────
@app.route('/api/awards/<int:award_id>/requirements', methods=['GET'])
def get_requirements(award_id):
    rows = db.fetchall("SELECT * FROM award_requirements WHERE awardId=? ORDER BY sortOrder, id", (award_id,))
    return jsonify(rows)

@app.route('/api/awards/<int:award_id>/requirements', methods=['POST'])
@require_admin
def add_requirement(award_id):
    d = request.json or {}
    text = d.get('text', '').strip()
    if not text:
        return jsonify({'error': 'text required'}), 400
    sort_order = db.scalar("SELECT COUNT(*) FROM award_requirements WHERE awardId=?", (award_id,))
    new_id = db.execute(
        "INSERT INTO award_requirements (awardId, text, completed, sortOrder) VALUES (?,?,0,?)",
        (award_id, text, sort_order)
    )
    row = db.fetchone("SELECT * FROM award_requirements WHERE id=?", (new_id,))
    return jsonify(row), 201

@app.route('/api/requirements/<int:req_id>', methods=['PATCH'])
@require_admin
def update_requirement(req_id):
    d = request.json or {}
    req = db.fetchone("SELECT * FROM award_requirements WHERE id=?", (req_id,))
    if not req:
        return jsonify({'error': 'Not found'}), 404
    text = d.get('text', req['text'])
    completed = int(d.get('completed', req['completed']))
    db.execute("UPDATE award_requirements SET text=?, completed=? WHERE id=?", (text, completed, req_id))
    # Auto-update parent award progress and status
    award_id = req['awardId']
    total = db.scalar("SELECT COUNT(*) FROM award_requirements WHERE awardId=?", (award_id,))
    done = db.scalar("SELECT COUNT(*) FROM award_requirements WHERE awardId=? AND completed=1", (award_id,))
    if total > 0:
        progress = round((done / total) * 100)
        if done == total:
            status = 'completed'
        elif done > 0:
            status = 'in_progress'
        else:
            status = 'not_started'
        db.execute("UPDATE awards SET progress=?, status=? WHERE id=?", (progress, status, award_id))
    row = db.fetchone("SELECT * FROM award_requirements WHERE id=?", (req_id,))
    return jsonify(row)

@app.route('/api/requirements/<int:req_id>', methods=['DELETE'])
@require_admin
def delete_requirement(req_id):
    req = db.fetchone("SELECT * FROM award_requirements WHERE id=?", (req_id,))
    if not req:
        return jsonify({'error': 'Not found'}), 404
    award_id = req['awardId']
    db.execute("DELETE FROM award_requirements WHERE id=?", (req_id,))
    # Recalculate progress after deletion
    total = db.scalar("SELECT COUNT(*) FROM award_requirements WHERE awardId=?", (award_id,))
    if total > 0:
        done = db.scalar("SELECT COUNT(*) FROM award_requirements WHERE awardId=? AND completed=1", (award_id,))
        progress = round((done / total) * 100)
        status = 'completed' if done == total else ('in_progress' if done > 0 else 'not_started')
        db.execute("UPDATE awards SET progress=?, status=? WHERE id=?", (progress, status, award_id))
    return jsonify({'success': True})

# ─── Event Routes ─────────────────────────────────────────────
@app.route('/api/events', methods=['GET'])
def get_events():
    rows = db.fetchall("SELECT * FROM events ORDER BY date, time")
    result = []
    for ev in rows:
        ev['signupCount'] = db.scalar("SELECT COUNT(*) FROM signups WHERE eventId=?", (ev['id'],))
        result.append(ev)
    return jsonify(result)

@app.route('/api/events/<int:event_id>', methods=['GET'])
def get_event(event_id):
    ev = db.fetchone("SELECT * FROM events WHERE id=?", (event_id,))
    if not ev:
        return jsonify({'error': 'Event not found'}), 404
    signups = db.fetchall("""
        SELECT s.id as scoutId, s.firstName, s.lastName, s.rank, s.den, s.grade,
               s.parentName, s.parentEmail, s.parentPhone,
               su.id as signupId, su.signupDate, su.notes as signupNotes
        FROM signups su JOIN scouts s ON su.scoutId = s.id
        WHERE su.eventId=? ORDER BY s.rank, s.lastName, s.firstName
    """, (event_id,))
    ev['signups'] = signups
    ev['signupCount'] = len(signups)
    return jsonify(ev)

@app.route('/api/events', methods=['POST'])
@require_admin
def create_event():
    d = request.json or {}
    if not d.get('title') or not d.get('date'):
        return jsonify({'error': 'title and date are required'}), 400
    new_id = db.execute(
        "INSERT INTO events (title,date,time,location,description,maxSignups) VALUES (?,?,?,?,?,?)",
        (d['title'],d['date'],d.get('time'),d.get('location'),d.get('description'),d.get('maxSignups') or None)
    )
    ev = db.fetchone("SELECT * FROM events WHERE id=?", (new_id,))
    ev['signupCount'] = 0
    return jsonify(ev), 201

@app.route('/api/events/<int:event_id>', methods=['PUT'])
@require_admin
def update_event(event_id):
    d = request.json or {}
    db.execute(
        "UPDATE events SET title=?,date=?,time=?,location=?,description=?,maxSignups=? WHERE id=?",
        (d.get('title'),d.get('date'),d.get('time'),d.get('location'),d.get('description'),d.get('maxSignups') or None, event_id)
    )
    ev = db.fetchone("SELECT * FROM events WHERE id=?", (event_id,))
    ev['signupCount'] = db.scalar("SELECT COUNT(*) FROM signups WHERE eventId=?", (event_id,))
    return jsonify(ev)

@app.route('/api/events/<int:event_id>', methods=['DELETE'])
@require_admin
def delete_event(event_id):
    db.execute("DELETE FROM events WHERE id=?", (event_id,))
    return jsonify({'success': True})

# ─── Signup Routes ───────────────────────────────────────────
@app.route('/api/signups', methods=['GET'])
def get_signups():
    event_id = request.args.get('eventId')
    scout_id = request.args.get('scoutId')
    if event_id:
        rows = db.fetchall("""
            SELECT su.*, s.firstName, s.lastName, s.rank, s.den, s.grade, s.parentName, s.parentPhone
            FROM signups su JOIN scouts s ON su.scoutId=s.id
            WHERE su.eventId=? ORDER BY s.rank, s.lastName, s.firstName
        """, (event_id,))
    elif scout_id:
        rows = db.fetchall("""
            SELECT su.*, e.title, e.date, e.time, e.location
            FROM signups su JOIN events e ON su.eventId=e.id
            WHERE su.scoutId=? ORDER BY e.date
        """, (scout_id,))
    else:
        rows = db.fetchall("SELECT * FROM signups ORDER BY signupDate DESC")
    return jsonify(rows)

@app.route('/api/signups', methods=['POST'])
def create_signup():
    d = request.json or {}
    scout_id = d.get('scoutId')
    event_id = d.get('eventId')
    if not scout_id or not event_id:
        return jsonify({'error': 'scoutId and eventId are required'}), 400
    ev = db.fetchone("SELECT * FROM events WHERE id=?", (event_id,))
    if not ev:
        return jsonify({'error': 'Event not found'}), 404
    if ev['maxSignups']:
        count = db.scalar("SELECT COUNT(*) FROM signups WHERE eventId=?", (event_id,))
        if count >= ev['maxSignups']:
            return jsonify({'error': 'Event is full'}), 409
    try:
        new_id = db.execute("INSERT INTO signups (scoutId,eventId,notes) VALUES (?,?,?)",
                            (scout_id, event_id, d.get('notes')))
        row = db.fetchone("SELECT * FROM signups WHERE id=?", (new_id,))
        return jsonify(row), 201
    except db.IntegrityError:
        return jsonify({'error': 'Scout is already signed up for this event'}), 409

@app.route('/api/signups', methods=['DELETE'])
def delete_signup():
    d = request.json or {}
    scout_id = d.get('scoutId')
    event_id = d.get('eventId')
    if not scout_id or not event_id:
        return jsonify({'error': 'scoutId and eventId required'}), 400
    db.execute("DELETE FROM signups WHERE scoutId=? AND eventId=?", (scout_id, event_id))
    return jsonify({'success': True})

@app.route('/api/signups/<int:signup_id>', methods=['DELETE'])
def delete_signup_by_id(signup_id):
    db.execute("DELETE FROM signups WHERE id=?", (signup_id,))
    return jsonify({'success': True})

# ─── Email Notification ──────────────────────────────────────
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def get_setting(key):
    row = db.fetchone("SELECT value FROM settings WHERE key=?", (key,))
    return row['value'] if row else None

def send_email_notification(subject, body_html):
    """Send email to pack leader. Returns True on success."""
    try:
        to_email   = get_setting('notification_email')
        smtp_user  = os.environ.get('SMTP_USER')  or get_setting('smtp_user')
        smtp_pass  = os.environ.get('SMTP_PASS')  or get_setting('smtp_pass')
        smtp_host  = os.environ.get('SMTP_HOST',  'smtp.gmail.com')
        smtp_port  = int(os.environ.get('SMTP_PORT', 587))
        if not to_email or not smtp_user or not smtp_pass:
            return False
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = smtp_user
        msg['To']      = to_email
        msg.attach(MIMEText(body_html, 'html'))
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo(); server.starttls(); server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [to_email], msg.as_string())
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

# ─── Sign-Up Slots Routes ────────────────────────────────────
@app.route('/api/events/<int:event_id>/slots', methods=['GET'])
def get_event_slots(event_id):
    slots = db.fetchall("SELECT * FROM event_slots WHERE eventId=? ORDER BY sortOrder, id", (event_id,))
    for slot in slots:
        slot['signups'] = db.fetchall("SELECT * FROM slot_signups WHERE slotId=? ORDER BY signupDate", (slot['id'],))
        slot['signupCount'] = len(slot['signups'])
    return jsonify(slots)

@app.route('/api/events/<int:event_id>/slots', methods=['POST'])
@require_admin
def create_slot(event_id):
    d = request.json or {}
    if not d.get('title'):
        return jsonify({'error': 'title is required'}), 400
    new_id = db.execute(
        "INSERT INTO event_slots (eventId, title, description, capacity, sortOrder) VALUES (?,?,?,?,?)",
        (event_id, d['title'], d.get('description'), d.get('capacity') or None, d.get('sortOrder', 0))
    )
    slot = db.fetchone("SELECT * FROM event_slots WHERE id=?", (new_id,))
    slot['signups'] = []; slot['signupCount'] = 0
    return jsonify(slot), 201

@app.route('/api/slots/<int:slot_id>', methods=['PUT'])
@require_admin
def update_slot(slot_id):
    d = request.json or {}
    db.execute(
        "UPDATE event_slots SET title=?, description=?, capacity=?, sortOrder=? WHERE id=?",
        (d.get('title'), d.get('description'), d.get('capacity') or None, d.get('sortOrder', 0), slot_id)
    )
    slot = db.fetchone("SELECT * FROM event_slots WHERE id=?", (slot_id,))
    slot['signups'] = db.fetchall("SELECT * FROM slot_signups WHERE slotId=? ORDER BY signupDate", (slot_id,))
    slot['signupCount'] = len(slot['signups'])
    return jsonify(slot)

@app.route('/api/slots/<int:slot_id>', methods=['DELETE'])
@require_admin
def delete_slot(slot_id):
    db.execute("DELETE FROM event_slots WHERE id=?", (slot_id,))
    return jsonify({'success': True})

@app.route('/api/slots/<int:slot_id>/signup', methods=['POST'])
def create_slot_signup(slot_id):
    d = request.json or {}
    name = (d.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400
    slot = db.fetchone("SELECT * FROM event_slots WHERE id=?", (slot_id,))
    if not slot:
        return jsonify({'error': 'Slot not found'}), 404
    if slot['capacity']:
        count = db.scalar("SELECT COUNT(*) FROM slot_signups WHERE slotId=?", (slot_id,))
        if count >= slot['capacity']:
            return jsonify({'error': 'This slot is full'}), 409
    new_id = db.execute(
        "INSERT INTO slot_signups (slotId, name, email, phone, notes) VALUES (?,?,?,?,?)",
        (slot_id, name, d.get('email'), d.get('phone'), d.get('notes'))
    )
    signup = db.fetchone("SELECT * FROM slot_signups WHERE id=?", (new_id,))
    try:
        ev = db.fetchone("SELECT title, date FROM events WHERE id=?", (slot['eventId'],))
        subject = f"New sign-up: {ev['title']} — {slot['title']}"
        lines = [f"<p><b>Event:</b> {ev['title']} on {ev['date']}</p>",
                 f"<p><b>Slot:</b> {slot['title']}</p>",
                 f"<p><b>Name:</b> {name}</p>"]
        if d.get('email'): lines.append(f"<p><b>Email:</b> {d['email']}</p>")
        if d.get('phone'): lines.append(f"<p><b>Phone:</b> {d['phone']}</p>")
        if d.get('notes'): lines.append(f"<p><b>Notes:</b> {d['notes']}</p>")
        send_email_notification(subject, "<h3>New Sign-Up Received ⚜️</h3>" + ''.join(lines))
    except Exception:
        pass
    return jsonify(signup), 201

@app.route('/api/slot-signups/<int:signup_id>', methods=['DELETE'])
@require_admin
def delete_slot_signup(signup_id):
    db.execute("DELETE FROM slot_signups WHERE id=?", (signup_id,))
    return jsonify({'success': True})

@app.route('/api/settings/notifications', methods=['GET'])
@require_admin
def get_notification_settings():
    result = {
        'notification_email': get_setting('notification_email') or '',
        'smtp_user':          get_setting('smtp_user') or '',
        'smtp_pass_set':      bool(get_setting('smtp_pass')),
    }
    return jsonify(result)

@app.route('/api/settings/notifications', methods=['PUT'])
@require_admin
def save_notification_settings():
    d = request.json or {}
    def upsert(key, value):
        if value is None: return
        if db.fetchone("SELECT key FROM settings WHERE key=?", (key,)):
            db.execute("UPDATE settings SET value=? WHERE key=?", (value, key))
        else:
            db.execute("INSERT INTO settings (key, value) VALUES (?,?)", (key, value), returning_id=False)
    upsert('notification_email', d.get('notification_email'))
    upsert('smtp_user', d.get('smtp_user'))
    if d.get('smtp_pass'):
        upsert('smtp_pass', d['smtp_pass'])
    return jsonify({'success': True})

# ─── Export Routes ───────────────────────────────────────────
def safe_filename(s):
    return ''.join(c if c.isalnum() or c in '-_' else '_' for c in s)[:60]

@app.route('/api/exports/all-scouts/csv')
@require_admin
def export_all_scouts_csv():
    rows = db.fetchall("SELECT * FROM scouts ORDER BY rank, lastName, firstName")
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(['First Name','Last Name','Rank','Den','Grade','Date Joined','Parent Name','Parent Email','Parent Phone','Notes'])
    for r in rows:
        w.writerow([r['firstName'],r['lastName'],r['rank'],r.get('den') or '',r.get('grade') or '',
                    r.get('dateJoined') or '',r.get('parentName') or '',r.get('parentEmail') or '',
                    r.get('parentPhone') or '',r.get('notes') or ''])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename="all_scouts.csv"'})

@app.route('/api/exports/event/<int:event_id>/csv')
@require_admin
def export_event_csv(event_id):
    ev = db.fetchone("SELECT * FROM events WHERE id=?", (event_id,))
    if not ev:
        return jsonify({'error': 'Event not found'}), 404
    rows = db.fetchall("""
        SELECT s.firstName,s.lastName,s.rank,s.den,s.grade,s.parentName,s.parentEmail,s.parentPhone,su.signupDate,su.notes
        FROM signups su JOIN scouts s ON su.scoutId=s.id WHERE su.eventId=?
        ORDER BY s.rank, s.lastName, s.firstName
    """, (event_id,))
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(['First Name','Last Name','Rank','Den','Grade','Parent Name','Parent Email','Parent Phone','Signup Date','Notes'])
    for r in rows:
        sd = str(r.get('signupDate') or '').split('T')[0].split(' ')[0]
        w.writerow([r['firstName'],r['lastName'],r['rank'],r.get('den') or '',r.get('grade') or '',
                    r.get('parentName') or '',r.get('parentEmail') or '',r.get('parentPhone') or '',sd,r.get('notes') or ''])
    output.seek(0)
    fname = f"{safe_filename(ev['title'])}_{ev['date']}_signups.csv"
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="{fname}"'})

@app.route('/api/exports/event/<int:event_id>/pdf')
@require_admin
def export_event_pdf(event_id):
    if not PDF_AVAILABLE:
        return jsonify({'error': 'PDF generation not available. Install reportlab.'}), 500
    ev = db.fetchone("SELECT * FROM events WHERE id=?", (event_id,))
    if not ev:
        return jsonify({'error': 'Event not found'}), 404
    signups = db.fetchall("""
        SELECT s.firstName,s.lastName,s.rank,s.den,s.grade,s.parentName,s.parentPhone
        FROM signups su JOIN scouts s ON su.scoutId=s.id WHERE su.eventId=?
        ORDER BY s.rank, s.lastName, s.firstName
    """, (event_id,))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch, leftMargin=0.6*inch, rightMargin=0.6*inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('title', fontSize=20, textColor=colors.HexColor('#FCC200'), alignment=TA_CENTER, fontName='Helvetica-Bold')
    sub_style = ParagraphStyle('sub', fontSize=13, textColor=colors.white, alignment=TA_CENTER)
    h2_style = ParagraphStyle('h2', fontSize=16, textColor=colors.HexColor('#003F87'), alignment=TA_CENTER, fontName='Helvetica-Bold', spaceAfter=4)
    info_style = ParagraphStyle('info', fontSize=11, textColor=colors.HexColor('#555555'), alignment=TA_CENTER, spaceAfter=2)

    story = []
    header_data = [[Paragraph('CUB SCOUTS PACK MANAGER', title_style)],
                   [Paragraph('Event Sign-Up Roster', sub_style)]]
    header_table = Table(header_data, colWidths=[7.3*inch])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#003F87')),
        ('TOPPADDING', (0,0), (-1,-1), 8), ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph(ev['title'], h2_style))
    date_str = ev['date'] + (f" at {ev['time']}" if ev['time'] else '')
    story.append(Paragraph(f"Date: {date_str}", info_style))
    if ev.get('location'):
        story.append(Paragraph(f"Location: {ev['location']}", info_style))
    story.append(Paragraph(f"Total Scouts Signed Up: {len(signups)}", info_style))
    story.append(Spacer(1, 0.15*inch))
    story.append(HRFlowable(width='100%', thickness=2, color=colors.HexColor('#003F87')))
    story.append(Spacer(1, 0.1*inch))

    if signups:
        table_data = [['Scout Name', 'Rank', 'Den', 'Grade', 'Parent / Guardian', 'Phone']]
        for s in signups:
            table_data.append([f"{s['firstName']} {s['lastName']}", s.get('rank') or '',
                               s.get('den') or '', s.get('grade') or '', s.get('parentName') or '', s.get('parentPhone') or ''])
        t = Table(table_data, colWidths=[1.8*inch, 0.9*inch, 0.6*inch, 0.7*inch, 1.6*inch, 1.0*inch])
        ts = TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#003F87')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 9),
            ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,1), (-1,-1), 8),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F0F4FF')]),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#DDDDDD')),
            ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
        ])
        t.setStyle(ts)
        story.append(t)
    else:
        story.append(Paragraph('No scouts have signed up yet.', styles['Normal']))

    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph(f"Generated {date.today().strftime('%B %d, %Y')} — Cub Scouts Pack Manager",
                            ParagraphStyle('footer', fontSize=8, textColor=colors.HexColor('#999999'), alignment=TA_CENTER)))
    doc.build(story)
    buf.seek(0)
    fname = f"{safe_filename(ev['title'])}_roster.pdf"
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=fname)

@app.route('/api/exports/scout/<int:scout_id>/pdf')
@require_admin
def export_scout_pdf(scout_id):
    if not PDF_AVAILABLE:
        return jsonify({'error': 'PDF generation not available. Install reportlab.'}), 500
    scout = db.fetchone("SELECT * FROM scouts WHERE id=?", (scout_id,))
    if not scout:
        return jsonify({'error': 'Scout not found'}), 404
    awards = db.fetchall("SELECT * FROM awards WHERE scoutId=? ORDER BY type, name", (scout_id,))
    events = db.fetchall("""
        SELECT e.title, e.date, e.time, e.location
        FROM signups su JOIN events e ON su.eventId=e.id
        WHERE su.scoutId=? ORDER BY e.date
    """, (scout_id,))

    RANK_COLORS = {'Lion':'#7B2D8B','Tiger':'#C2410C','Wolf':'#374151','Bear':'#92400E','Webelos':'#065F46','AOL':'#1E3A8A'}
    rank_color = RANK_COLORS.get(scout['rank'], '#003F87')

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch, leftMargin=0.6*inch, rightMargin=0.6*inch)
    styles = getSampleStyleSheet()

    def ps(name, **kwargs):
        return ParagraphStyle(name, **kwargs)

    story = []
    title_style = ps('t', fontSize=18, textColor=colors.HexColor('#FCC200'), alignment=TA_CENTER, fontName='Helvetica-Bold')
    sub_style = ps('s', fontSize=11, textColor=colors.white, alignment=TA_CENTER)
    header_data = [[Paragraph('CUB SCOUTS PACK MANAGER', title_style)],
                   [Paragraph('Scout Profile Report', sub_style)]]
    header_table = Table(header_data, colWidths=[7.3*inch])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#003F87')),
        ('TOPPADDING', (0,0), (-1,-1), 8), ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.15*inch))

    rank_label = 'Arrow of Light' if scout['rank'] == 'AOL' else scout['rank']
    name_style = ps('nm', fontSize=22, textColor=colors.HexColor(rank_color), fontName='Helvetica-Bold')
    rank_style = ps('rk', fontSize=12, textColor=colors.HexColor('#555555'))

    den_grade = ' · '.join(filter(None, [scout.get('den'), scout.get('grade')]))
    info_box = [[Paragraph(f"{scout['firstName']} {scout['lastName']}", name_style)],
                [Paragraph(f"{rank_label} Scout  {('· ' + den_grade) if den_grade else ''}", rank_style)]]
    ib_table = Table(info_box, colWidths=[7.3*inch])
    ib_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor(rank_color + '20')),
        ('LEFTPADDING', (0,0), (-1,-1), 12), ('TOPPADDING', (0,0), (-1,-1), 8), ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LINEBELOW', (0,-1), (-1,-1), 2, colors.HexColor(rank_color)),
    ]))
    story.append(ib_table)
    story.append(Spacer(1, 0.1*inch))

    if scout.get('parentName') or scout.get('parentEmail') or scout.get('parentPhone'):
        contact = ' · '.join(filter(None, [scout.get('parentName'), scout.get('parentEmail'), scout.get('parentPhone')]))
        story.append(Paragraph(f"Contact: {contact}", ps('c', fontSize=10, textColor=colors.HexColor('#333333'))))

    completed_a = [a for a in awards if a['status'] == 'completed']
    in_progress_a = [a for a in awards if a['status'] == 'in_progress']
    not_started_a = [a for a in awards if a['status'] == 'not_started']

    story.append(Spacer(1, 0.1*inch))
    stats_data = [[
        Paragraph(f'<font size="20"><b>{len(completed_a)}</b></font><br/><font color="#059669">Completed</font>', ps('sd', alignment=TA_CENTER, fontSize=10, textColor=colors.HexColor('#059669'))),
        Paragraph(f'<font size="20"><b>{len(in_progress_a)}</b></font><br/><font color="#D97706">In Progress</font>', ps('si', alignment=TA_CENTER, fontSize=10, textColor=colors.HexColor('#D97706'))),
        Paragraph(f'<font size="20"><b>{len(not_started_a)}</b></font><br/><font color="#9CA3AF">Not Started</font>', ps('sn', alignment=TA_CENTER, fontSize=10, textColor=colors.HexColor('#9CA3AF'))),
    ]]
    stats_table = Table(stats_data, colWidths=[2.4*inch, 2.4*inch, 2.5*inch])
    stats_table.setStyle(TableStyle([
        ('TOPPADDING', (0,0), (-1,-1), 6), ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('BACKGROUND', (0,0), (0,0), colors.HexColor('#ECFDF5')),
        ('BACKGROUND', (1,0), (1,0), colors.HexColor('#FFFBEB')),
        ('BACKGROUND', (2,0), (2,0), colors.HexColor('#F9FAFB')),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))
    story.append(stats_table)
    story.append(Spacer(1, 0.15*inch))

    def section_header(title, color):
        t = Table([[Paragraph(title, ps('sh', fontSize=11, textColor=colors.white, fontName='Helvetica-Bold'))]], colWidths=[7.3*inch])
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor(color)),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('LEFTPADDING',(0,0),(-1,-1),8)]))
        story.append(t)
        story.append(Spacer(1, 0.05*inch))

    def award_rows(award_list):
        if not award_list: return
        data = [['Award Name', 'Type', 'Status']]
        for a in award_list:
            type_label = a['type'].replace('_',' ').title()
            status_label = {
                'completed': f"✓ Completed{' ' + a['dateEarned'] if a.get('dateEarned') else ''}",
                'in_progress': f"◑ {a['progress']}% complete",
                'not_started': '○ Not started'
            }.get(a['status'], a['status'])
            data.append([a['name'], type_label, status_label])
        t = Table(data, colWidths=[3.2*inch, 1.8*inch, 2.3*inch])
        status_colors_map = {'completed': '#059669', 'in_progress': '#D97706', 'not_started': '#9CA3AF'}
        ts = TableStyle([
            ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E5E7EB')),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8),
            ('FONTNAME',(0,1),(-1,-1),'Helvetica'),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F9FAFB')]),
            ('GRID',(0,0),(-1,-1),0.5,colors.HexColor('#E5E7EB')),
            ('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3),('LEFTPADDING',(0,0),(-1,-1),5),
        ])
        for i, a in enumerate(award_list, 1):
            c = colors.HexColor(status_colors_map.get(a['status'], '#9CA3AF'))
            ts.add('TEXTCOLOR',(2,i),(2,i),c)
        t.setStyle(ts)
        story.append(t)
        story.append(Spacer(1, 0.1*inch))

    if completed_a: section_header(f'Completed Awards ({len(completed_a)})', '#059669'); award_rows(completed_a)
    if in_progress_a: section_header(f'In Progress ({len(in_progress_a)})', '#D97706'); award_rows(in_progress_a)
    if not_started_a: section_header(f'Not Started ({len(not_started_a)})', '#9CA3AF'); award_rows(not_started_a)

    section_header(f'Registered Events ({len(events)})', '#003F87')
    if events:
        ev_data = [['Event','Date','Location']]
        for e in events:
            ev_data.append([e['title'], e['date'] + (' at ' + e['time'] if e.get('time') else ''), e.get('location') or ''])
        et = Table(ev_data, colWidths=[3.0*inch, 1.8*inch, 2.5*inch])
        et.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E5E7EB')),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8),
            ('FONTNAME',(0,1),(-1,-1),'Helvetica'),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#EFF6FF')]),
            ('GRID',(0,0),(-1,-1),0.5,colors.HexColor('#E5E7EB')),
            ('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3),('LEFTPADDING',(0,0),(-1,-1),5),
        ]))
        story.append(et)
    else:
        story.append(Paragraph('No events registered.', styles['Normal']))

    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph(f"Generated {date.today().strftime('%B %d, %Y')} — Cub Scouts Pack Manager",
                            ps('ft', fontSize=8, textColor=colors.HexColor('#999999'), alignment=TA_CENTER)))

    doc.build(story)
    buf.seek(0)
    fname = f"{safe_filename(scout['firstName'] + '_' + scout['lastName'])}_profile.pdf"
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=fname)

# ─── Static Files ─────────────────────────────────────────────
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    if path and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

# ─── Startup ──────────────────────────────────────────────────
# init_db() runs at module load so it works with both direct python3 AND gunicorn
init_db()

if __name__ == '__main__':
    db_mode = 'PostgreSQL' if db.is_pg else f'SQLite ({DB_PATH})'
    print()
    print("  ⚜️  ================================")
    print("      CUB SCOUTS PACK MANAGER")
    print("  ⚜️  ================================")
    print(f"  🌐  Running at: http://localhost:{PORT}")
    print(f"  💾  Database:   {db_mode}")
    print(f"  🔐  Admin password: cubmaster123")
    print(f"       (change in Admin > Settings)")
    print("  ================================")
    print()
    app.run(host='0.0.0.0', port=PORT, debug=False)
