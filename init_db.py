import sqlite3

DB = "saranalayam.db"

db = sqlite3.connect(DB)
cur = db.cursor()

# ---------- ADMINS TABLE ----------
cur.execute("""
CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    email TEXT
)
""")

# ---------- USERS TABLE ----------
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT UNIQUE,
    password TEXT
)
""")

# ---------- DONATIONS TABLE ----------
cur.execute("""
CREATE TABLE IF NOT EXISTS donation_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email TEXT,
    donor_name TEXT,
    email TEXT,
    phone TEXT,
    country TEXT,
    amount REAL,
    purpose TEXT,
    payment_method TEXT,
    date TEXT,
    qr_id TEXT UNIQUE
)
""")

# ---------- DAILY RECORDS TABLE ----------
cur.execute("""
CREATE TABLE IF NOT EXISTS daily_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    total_inmates INTEGER,
    hospitalized INTEGER,
    staff_count INTEGER
)
""")

# ---------- DEFAULT ADMIN ----------
cur.execute("""
            INSERT INTO admins (username, password, email)
VALUES ('admin', 'admin123', 'admin@saranalayam.org')
""")


db.commit()
db.close()

print("✅ Database initialized with admin user")
