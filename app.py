from flask import Flask, render_template, request, redirect, session
import sqlite3
import random
from datetime import date
import smtplib
from email.message import EmailMessage

app = Flask(__name__)
app.secret_key = 'saranalayam_secret'

DB = 'saranalayam.db'

# ================= DATABASE =================
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

# ================= EMAIL OTP =================
def send_otp(email, otp):
    msg = EmailMessage()
    msg.set_content(f"Your OTP for password reset is: {otp}")
    msg['Subject'] = 'Saranalayam Admin Password Reset'
    msg['From'] = 'YOUR_EMAIL@gmail.com'
    msg['To'] = email

    server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
    server.login('YOUR_EMAIL@gmail.com', 'YOUR_APP_PASSWORD')
    server.send_message(msg)
    server.quit()

# ================= PUBLIC PAGES =================
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

# ================= DONATION STEP 1 =================
@app.route('/donate', methods=['GET'])
def donate():
    return render_template('donate.html')

# ================= DONATION STEP 2 =================
@app.route('/donation-step2', methods=['POST'])
def donation_step2():
    # Save Step 1 info into session
    session['donor_info'] = request.form.to_dict()
    return render_template('donate_2.html')

# ================= DONATION FINAL SUBMIT =================
@app.route('/donate-submit', methods=['POST'])
def donate_submit():
    donor_info = session.get('donor_info')
    if not donor_info:
        return redirect('/donate')

    # ---------- STEP 1 DATA ----------
    donor_name = donor_info.get('first_name', '') + " " + donor_info.get('last_name', '')
    email = donor_info.get('email', '')

    # Country
    country = donor_info.get('country', '')
    if country.lower() == 'other':
        country = donor_info.get('custom_country', '')
        # Phone
    country_code = donor_info.get('country_code', '')
    if country_code.lower() == 'other':
        country_code = donor_info.get('custom_country_code', '')
    phone = f"{country_code}{donor_info.get('phone', '')}"

    # ---------- STEP 2 DATA ----------
    amount = request.form.get('amount')
    purpose = request.form.get('purpose', 'General Support')
    payment_method = request.form.get('payment_method')

    if not amount or not payment_method:
        return redirect('/donate')

    # Generate unique QR
    qr = 'SAR' + str(random.randint(10000, 99999))

    # ---------- INSERT INTO donation_summary ----------
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO donation_summary 
        (donor_name, email, phone, country, amount, purpose, payment_method, date, qr_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        donor_name,
        email,
        phone,
        country,
        amount,
        purpose,
        payment_method,
        str(date.today()),
        qr
    ))
    db.commit()
    db.close()

    # Clear session
    session.pop('donor_info', None)

    # ---------- RENDER SUCCESS ----------
    return render_template(
        'success.html',
        donor=donor_name,
        amount=amount,
        payment_method=payment_method,
        qr=qr
    )


# ================= ADMIN LOGIN =================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'attempts' not in session:
        session['attempts'] = 0
    if 'lock_time' not in session:
        session['lock_time'] = None

    if request.method == 'POST':
        if session['attempts'] >= 3:
            return render_template('login.html', error="Account locked. Try later.")

        username = request.form['username']
        password = request.form['password']

        db = get_db()
        cur = db.cursor()
        cur.execute('SELECT * FROM admins WHERE username=? AND password=?', (username, password))
        admin = cur.fetchone()
        db.close()

        if admin:
            session.clear()
            session['admin'] = username
            return redirect('/dashboard')

        session['attempts'] += 1
        return render_template('login.html', error="Invalid credentials")

    return render_template('login.html')

# ================= DASHBOARD =================
@app.route('/dashboard')
def dashboard():
    if 'admin' not in session:
        return redirect('/login')

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM daily_records ORDER BY id DESC LIMIT 1")
    latest = cur.fetchone()
    db.close()

    return render_template('admin_dashboard.html', latest=latest)

# ================= DONATION LIST =================
@app.route('/donations')
def donation_list():
    if 'admin' not in session:
        return redirect('/login')

    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT * FROM donations ORDER BY id DESC')
    donations = cur.fetchall()
    db.close()

    return render_template('donations.html', donations=donations)

# ================= DAILY RECORDS =================
@app.route('/records', methods=['GET', 'POST'])
def records():
    if 'admin' not in session:
        return redirect('/login')

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM daily_records ORDER BY id DESC LIMIT 1")
    record = cur.fetchone()

    if request.method == 'POST':
        inmates = request.form['inmates']
        hospitalized = request.form['hospitalized']
        staff = request.form['staff']

        if record:
            cur.execute("""
                UPDATE daily_records
                SET total_inmates=?, hospitalized=?, staff_count=?
                WHERE id=?
            """, (inmates, hospitalized, staff, record['id']))
        else:
            cur.execute("""
                INSERT INTO daily_records VALUES (NULL,?,?,?,?)
            """, (str(date.today()), inmates, hospitalized, staff))

        db.commit()
        db.close()
        return redirect('/dashboard')

    db.close()
    return render_template('records.html', record=record)

# ================= VERIFY QR =================
@app.route('/verify', methods=['GET', 'POST'])
def verify():
    if request.method == 'POST':
        qr = request.form['qr']
        db = get_db()
        cur = db.cursor()
        cur.execute('SELECT * FROM donations WHERE qr_id=?', (qr,))
        result = cur.fetchone()
        db.close()
        return 'Valid Donation' if result else 'Invalid QR'

    return render_template('verify.html')

# ================= PASSWORD RESET =================
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        otp = str(random.randint(100000, 999999))
        session['otp'] = otp
        session['email'] = email
        send_otp(email, otp)
        return redirect('/verify-otp')

    return render_template('forgot_password.html')

@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    if request.method == 'POST':
        if request.form['otp'] == session.get('otp'):
            return redirect('/reset-password')
        return 'Invalid OTP'
    return render_template('verify_otp.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        pwd = request.form['password']
        email = session['email']

        db = get_db()
        cur = db.cursor()
        cur.execute('UPDATE admins SET password=? WHERE email=?', (pwd, email))
        db.commit()
        db.close()

        session.clear()
        return redirect('/login')

    return render_template('reset_password.html')

# ================= LOGOUT =================
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# ================= RUN =================
if __name__ == '__main__':
    app.run(debug=True)
