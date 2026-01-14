import sqlite3

db = sqlite3.connect("saranalayam.db")
cur = db.cursor()

# ---------- ADMINS TABLE ----------
cur.execute("""
CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT
)
""")

# Check if 'email' column exists, add if missing
cur.execute("PRAGMA table_info(admins)")
columns = [col[1] for col in cur.fetchall()]
if 'email' not in columns:
    cur.execute("ALTER TABLE admins ADD COLUMN email TEXT")

# ---------- DONATIONS TABLE ----------
cur.execute("""
CREATE TABLE IF NOT EXISTS donations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    donor TEXT,
    amount INTEGER,
    date TEXT,
    qr_id TEXT UNIQUE
)
""")

# ---------- DAILY RECORDS TABLE ----------
cur.execute("""
CREATE TABLE IF NOT EXISTS daily_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    inmates INTEGER,
    hospitalized INTEGER,
    staff INTEGER
)
""")

# ---------- DEFAULT ADMIN ----------
cur.execute("""
INSERT OR IGNORE INTO admins (username, password, email)
VALUES ('admin', 'admin123', 'admin@saranalayam.org')
""")

db.commit()
db.close()

print("✅ Database initialized successfully with email field")
