from flask import Flask, render_template, request, redirect, session
import sqlite3
import random
from datetime import date
import smtplib
from email.message import EmailMessage
import os
# 👉 ADD THIS LINE HERE
from send_otp import send_otp

app = Flask(__name__)
app.secret_key = 'saranalayam_secret'

DB = 'saranalayam.db'

# ================= DATABASE =================
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

# ================= INIT DATABASE =================
def init_db():
    if not os.path.exists(DB):
        db = sqlite3.connect(DB)
        cur = db.cursor()

        cur.execute("""
        CREATE TABLE admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            email TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            password TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE donation_summary (
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

        cur.execute("""
        CREATE TABLE daily_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            total_inmates INTEGER,
            hospitalized INTEGER,
            staff_count INTEGER
        )
        """)

        # default admin
        cur.execute("""
        INSERT INTO admins (username, password, email)
        VALUES ('admin', 'admin123', 'admin@saranalayam.org')
        """)

        db.commit()
        db.close()

# ================= PUBLIC =================
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form['identifier']  # user enters email
        password = request.form['password']

        db = get_db()
        cur = db.cursor()

        # 1️⃣ Check if identifier matches any ADMIN username or email
        cur.execute("SELECT * FROM admins WHERE username=? OR email=?", (identifier, identifier))
        admin = cur.fetchone()
        if admin and admin['password'] == password:
            session.clear()
            session['admin'] = admin['username']
            db.close()
            return redirect('/admin')  # admin dashboard

        # 2️⃣ Check USER login (email only)
        cur.execute("SELECT * FROM users WHERE email=?", (identifier,))
        user = cur.fetchone()
        if user and user['password'] == password:
            session.clear()
            session['user'] = user['email']
            db.close()
            return redirect('/user-dashboard')  # user dashboard

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

        db = get_db()
        cur = db.cursor()
        try:
            cur.execute(
                "INSERT INTO users (name, email, password) VALUES (?,?,?)",
                (name, email, password)
            )
            db.commit()
            db.close()
            return redirect('/login')
        except sqlite3.IntegrityError:
            db.close()
            return render_template('register.html', error="Email already exists")

    return render_template('register.html')

# ================= DONATION =================
@app.route('/donate', methods=['GET', 'POST'])
def donate():
    if 'user' not in session:
        return render_template('donate.html')  # will show login message

    return render_template('donate.html')


    if request.method == 'POST':
        session['donor_info'] = request.form.to_dict()
        return redirect('/donation-step2')

    return render_template('donate.html')

@app.route('/donation-step2', methods=['GET', 'POST'])
def donation_step2():
    if 'user' not in session or 'donor_info' not in session:
        return redirect('/login')

    if request.method == 'POST':
        return redirect('/donate-submit')

    return render_template('donate_2.html')

@app.route('/donate-submit', methods=['POST'])
def donate_submit():
    if 'user' not in session or 'donor_info' not in session:
        return redirect('/login')

    donor = session.get('donor_info', {})
    amount = request.form['amount']
    purpose = request.form['purpose']
    payment_method = request.form['payment_method']

    qr = 'SAR' + str(random.randint(10000, 99999))

    first_name = donor.get('first_name', '')
    last_name = donor.get('last_name', '')
    donor_name = first_name + " " + last_name

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO donation_summary
        (user_email, donor_name, email, phone, country, amount, purpose, payment_method, date, qr_id)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (
        session['user'],
        donor_name,
        donor.get('email', ''),
        donor.get('phone', ''),
        donor.get('country', ''),
        amount,
        purpose,
        payment_method,
        str(date.today()),
        qr
    ))
    db.commit()
    db.close()

    session.pop('donor_info', None)

    return render_template(
        'success.html',
        qr=qr,
        donor_name=donor_name,
        amount=amount,
        payment_method=payment_method
    )

# ================= ADMIN DASHBOARD =================
@app.route('/admin')
def admin_dashboard():
    if 'admin' not in session:
        return redirect('/login')
    return render_template('admin_dashboard.html')

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
            INSERT INTO daily_records (date, total_inmates, hospitalized, staff_count)
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

    cur.execute("""
        SELECT donor_name, amount, purpose, payment_method, date, qr_id
        FROM donation_summary
        WHERE user_email=?
        ORDER BY id DESC
    """, (session['user'],))

    donations = cur.fetchall()
    db.close()

    return render_template('my_donations.html', donations=donations)

# ---------------- FORGOT PASSWORD ----------------
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email'].strip()
        otp = str(random.randint(100000, 999999))

        db = get_db()
        cur = db.cursor()

        # Check if email exists in admins
        cur.execute("SELECT * FROM admins WHERE email=?", (email,))
        admin = cur.fetchone()

        if admin:
            session['reset_role'] = 'admin'
            session['reset_email'] = admin['email']
        else:
            # Check if email exists in users
            cur.execute("SELECT * FROM users WHERE email=?", (email,))
            user = cur.fetchone()
            if not user:
                db.close()
                return render_template('forgot_password.html', error="Email not found")
            session['reset_role'] = 'user'
            session['reset_email'] = user['email']

        db.close()

        # Store OTP in session
        session['otp'] = otp

        # Send OTP to the email
        success = send_otp(email, otp)
        if not success:
            return render_template('forgot_password.html', error="Failed to send OTP. Try again later.")

        return redirect('/verify-otp')

    return render_template('forgot_password.html')


# ---------------- VERIFY OTP ----------------
@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    if request.method == 'POST':
        entered_otp = request.form['otp'].strip()
        if entered_otp == session.get('otp'):
            session.pop('otp')  # Remove OTP after verification
            return redirect('/reset-password')
        else:
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

        db = get_db()
        cur = db.cursor()

        if role == 'admin':
            cur.execute("UPDATE admins SET password=? WHERE email=?", (new_password, email))
        else:
            cur.execute("UPDATE users SET password=? WHERE email=?", (new_password, email))

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
