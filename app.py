from flask import Flask, render_template, request, redirect, session
import sqlite3
import random
from datetime import date
import os
from werkzeug.security import generate_password_hash, check_password_hash
from send_otp import send_otp

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "saranalayam_secret")

DB = 'saranalayam.db'


# ================= DATABASE =================
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


# ================= INIT DATABASE =================
def init_db():
    db = sqlite3.connect(DB)
    cur = db.cursor()

    # ADMINS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        email TEXT UNIQUE
    )
    """)

    # USERS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT
    )
    """)

    # DONATIONS
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

    # DAILY RECORDS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS daily_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        total_inmates INTEGER,
        hospitalized INTEGER,
        staff_count INTEGER
    )
    """)

    # DEFAULT ADMIN (only if not exists)
    cur.execute("SELECT * FROM admins WHERE username='admin'")
    if not cur.fetchone():
        hashed_password = generate_password_hash("admin123")
        cur.execute("""
        INSERT INTO admins (username, password, email)
        VALUES (?, ?, ?)
        """, ("admin", hashed_password, "admin@saranalayam.org"))

    db.commit()
    db.close()


# ================= PUBLIC ROUTES =================
@app.route('/')
def home():
    return render_template('home.html')


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/contact')
def contact():
    return render_template('contact.html')


# ================= LOGIN (ADMIN + USER) =================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form['identifier'].strip()
        password = request.form['password'].strip()

        db = get_db()
        cur = db.cursor()

        # ---- ADMIN CHECK ----
        cur.execute("SELECT * FROM admins WHERE username=? OR email=?", (identifier, identifier))
        admin = cur.fetchone()
        if admin and check_password_hash(admin['password'], password):
            session.clear()
            session['admin'] = admin['username']
            db.close()
            return redirect('/admin')

        # ---- USER CHECK ----
        cur.execute("SELECT * FROM users WHERE email=?", (identifier,))
        user = cur.fetchone()
        if user and check_password_hash(user['password'], password):
            session.clear()
            session['user'] = user['email']
            session['user_name'] = user['name']
            db.close()
            return redirect('/user-dashboard')

        db.close()
        return render_template('login.html', error="Invalid credentials")

    return render_template('login.html')


# ================= REGISTER =================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        hashed_password = generate_password_hash(password)

        db = get_db()
        cur = db.cursor()

        try:
            cur.execute(
                "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                (name, email, hashed_password)
            )
            db.commit()
            return redirect('/login')
        except:
            return render_template('register.html', error="Email already exists")
        finally:
            db.close()

    return render_template('register.html')


# ================= DONATION STEP 1 =================
@app.route('/donate', methods=['GET', 'POST'])
def donate():
    if 'user' not in session:
        return render_template('donate.html')

    if request.method == 'POST':
        session['donor_info'] = request.form.to_dict()
        return redirect('/donation-step2')

    return render_template('donate.html')


# ================= DONATION STEP 2 =================
@app.route('/donation-step2')
def donation_step2():
    if 'donor_info' not in session:
        return redirect('/donate')
    return render_template('donate_2.html')


# ================= DONATION SUBMIT =================
@app.route('/donate-submit', methods=['POST'])
def donate_submit():
    if 'donor_info' not in session:
        return redirect('/donate')

    donor = session['donor_info']

    amount = float(request.form['amount'])
    purpose = request.form['purpose']
    payment_method = request.form['payment_method']

    country = donor.get('country')
    if country == "other":
        country = donor.get('custom_country')

    code = donor.get('country_code')
    if code == "other":
        code = donor.get('custom_country_code')

    full_phone = f"{code} {donor.get('phone')}"
    qr_id = "TXN" + str(random.randint(100000, 999999))
    today = date.today().strftime("%Y-%m-%d")

    db = get_db()
    cur = db.cursor()

    cur.execute("""
        INSERT INTO donation_summary
        (user_email, donor_name, email, phone, country,
         amount, purpose, payment_method, date, qr_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session['user'],
        donor.get('first_name') + " " + donor.get('last_name'),
        donor.get('email'),
        full_phone,
        country,
        amount,
        purpose,
        payment_method,
        today,
        qr_id
    ))

    db.commit()
    db.close()

    session.pop('donor_info', None)

    return render_template(
        'success.html',
        donor_name=donor.get('first_name') + " " + donor.get('last_name'),
        amount=amount,
        payment_method=payment_method,
        qr=qr_id
    )


# ================= USER DASHBOARD =================
@app.route('/user-dashboard')
def user_dashboard():
    if 'user' not in session:
        return redirect('/login')
    return render_template('user_dashboard.html')


@app.route('/my-donations')
def my_donations():
    if 'user' not in session:
        return redirect('/login')

    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT * FROM donation_summary WHERE user_email=? ORDER BY date DESC",
        (session['user'],)
    )
    donations = cur.fetchall()
    db.close()

    return render_template('my_donation.html', donations=donations)


# ================= ADMIN DASHBOARD =================
@app.route('/admin')
def admin_dashboard():
    if 'admin' not in session:
        return redirect('/login')

    db = get_db()
    cur = db.cursor()

    cur.execute("SELECT COUNT(*) FROM donation_summary")
    total_donations = cur.fetchone()[0]

    cur.execute("SELECT SUM(amount) FROM donation_summary")
    total_amount = cur.fetchone()[0] or 0

    db.close()

    return render_template(
        'admin_dashboard.html',
        total_donations=total_donations,
        total_amount=total_amount
    )


@app.route('/admin/donations')
def admin_donations():
    if 'admin' not in session:
        return redirect('/login')

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM donation_summary ORDER BY date DESC")
    donations = cur.fetchall()
    db.close()

    return render_template('admin_donations.html', donations=donations)


@app.route('/admin/update', methods=['GET', 'POST'])
def admin_update():
    if 'admin' not in session:
        return redirect('/login')

    db = get_db()
    cur = db.cursor()

    if request.method == 'POST':
        cur.execute("""
            INSERT INTO daily_records
            (date, total_inmates, hospitalized, staff_count)
            VALUES (?,?,?,?)
        """, (
            str(date.today()),
            request.form['total_inmates'],
            request.form['hospitalized'],
            request.form['staff_count']
        ))
        db.commit()
        db.close()
        return redirect('/admin')

    cur.execute("SELECT * FROM daily_records ORDER BY id DESC LIMIT 1")
    record = cur.fetchone()
    db.close()

    return render_template('admin_update.html', record=record)


# ================= FORGOT PASSWORD =================
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email'].strip()
        otp = str(random.randint(100000, 999999))

        db = get_db()
        cur = db.cursor()

        cur.execute("SELECT * FROM admins WHERE email=?", (email,))
        admin = cur.fetchone()

        if admin:
            session['reset_role'] = 'admin'
            session['reset_email'] = email
        else:
            cur.execute("SELECT * FROM users WHERE email=?", (email,))
            user = cur.fetchone()
            if not user:
                db.close()
                return render_template('forgot_password.html', error="Email not found")
            session['reset_role'] = 'user'
            session['reset_email'] = email

        db.close()

        session['otp'] = otp

        if not send_otp(email, otp):
            return render_template('forgot_password.html', error="Failed to send OTP")

        return redirect('/verify-otp')

    return render_template('forgot_password.html')

# ---------------- VERIFY OTP ----------------
@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    if request.method == 'POST':
        if request.form['otp'].strip() == session.get('otp'):
            session.pop('otp')
            return redirect('/reset-password')
        return render_template('verify_otp.html', error="Invalid OTP")

    return render_template('verify_otp.html')

# ---------------- RESET PASSWORD ----------------
@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        new_password = request.form['password'].strip()
        role = session.get('reset_role')
        email = session.get('reset_email')

        if not role or not email:
            return redirect('/forgot-password')

        hashed = generate_password_hash(new_password)

        db = get_db()
        cur = db.cursor()

        if role == 'admin':
            cur.execute("UPDATE admins SET password=? WHERE email=?", (hashed, email))
        else:
            cur.execute("UPDATE users SET password=? WHERE email=?", (hashed, email))

        db.commit()
        db.close()

        session.clear()
        return redirect('/login')

    return render_template('reset_password.html')


# ================= LOGOUT =================
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


# ================= RUN =================
if __name__ == '__main__':
    init_db()
    app.run(debug=True)
