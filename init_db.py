import sqlite3
from werkzeug.security import generate_password_hash


DB = "saranalayam.db"


def init_db():
    db = sqlite3.connect(DB)
    cur = db.cursor()

    # ================= ADMINS =================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        email TEXT UNIQUE
    )
    """)

    # ================= USERS =================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT
    )
    """)

    # ================= DONATIONS =================
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
        qr_id TEXT UNIQUE,
        payment_id TEXT,
        order_id TEXT,
        status TEXT DEFAULT 'Pending'
    )
    """)

    # ---------- DAILY RECORDS ----------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS daily_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT UNIQUE,  -- Added UNIQUE here to support REPLACE logic
        total_inmates INTEGER,
        active_inmates INTEGER,  -- Ensure this is added
        hospitalized INTEGER,
        discharged INTEGER,
        deceased INTEGER,
        male_inmates INTEGER,
        female_inmates INTEGER,
        new_inmates INTEGER,
        staff_count INTEGER,
        guests_arrived INTEGER
    )
    """)

        # ---------- INMATES ----------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS inmates(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        age INTEGER,
        gender TEXT,
        admission_date TEXT,
        status TEXT,
        illness TEXT,
        hospital_details TEXT,
        notes TEXT,
        date_of_death TEXT,
        previous_status TEXT,
        status_updated_date TEXT
    )
    """)
    
    # BLOG POSTS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS blog_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        image_filename TEXT,
        date_posted TEXT
    )
    """)


    #================== QUESTIONS =================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT,
        question TEXT,
        reply TEXT,
        status TEXT DEFAULT 'Pending',
        date TEXT
    )
    """)

    # ================= DEFAULT ADMIN =================
    cur.execute("SELECT * FROM admins WHERE username='admin'")
    if not cur.fetchone():
        hashed_password = generate_password_hash("admin123")
        cur.execute("""
        INSERT INTO admins (username, password, email)
        VALUES (?, ?, ?)
        """, ("admin", hashed_password, "admin@saranalayam.org"))

    db.commit()
    db.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
