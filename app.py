from flask import Flask, render_template, request, redirect, session
import sqlite3
import random
from datetime import date
import os
from werkzeug.security import generate_password_hash, check_password_hash
from send_otp import send_otp
import razorpay
from razorpay_utils import client as razorpay_client, RAZORPAY_KEY_ID
from razorpay_utils import create_order
from razorpay_utils import verify_payment_signature
from receipt_utils import generate_receipt
from flask import send_file


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "saranalayam_secret")

DB = 'saranalayam.db'


# ================= DATABASE =================#
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


# ================= INIT DATABASE =================#
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
    qr_id TEXT UNIQUE,
    payment_id TEXT,
    order_id TEXT,
    status TEXT DEFAULT 'Pending'
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

    #QUESTIONS
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


# ================= PUBLIC ROUTES =================#
@app.route('/')
def home():
    return render_template('home.html')


@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/faq')
def faq():
    return render_template('faq.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')


# ================= LOGIN (ADMIN + USER) =================#
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


# ================= REGISTER =================#
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

# ================= DONATION STEP 1 =================#
@app.route('/donate', methods=['GET', 'POST'])
def donate():
    if 'user' in session:
        if request.method == 'POST':
            session['donor_info'] = {
                "first_name": request.form['first_name'],
                "last_name": request.form['last_name'],
                "email": request.form['email'],
                "phone": request.form['phone'],
                "country": request.form.get('country')
            }
            return redirect('/donate-step-2')
        return render_template('donate.html', user_name=session.get('user_name'))
    else:
        # Guest sees login prompt
        return render_template('donate.html')

# ================= DONATION STEP 2 =================#
@app.route('/donate-step-2', methods=['GET', 'POST'])
def donate_step_2():
    if 'user' not in session:
        return redirect('/login')
    if 'donor_info' not in session:
        return redirect('/donate')

    donor = session['donor_info']

    if request.method == 'POST':

        # Get amount
        try:
            amount = float(request.form['amount'])
            if amount <= 0:
                raise ValueError
        except:
            return render_template("donate_2.html", donor=donor, error="Enter a valid amount")

        # Get purpose
        purpose = request.form.get("purpose")

        if purpose == "Other":
            purpose = request.form.get("other_purpose", "").strip()
            if not purpose:
                return render_template(
                    "donate_2.html",
                    donor=donor,
                    error="Please specify the purpose"
                )

        # Get payment method
        payment_method = request.form['payment_method']

        # Save donation info in session
        session['donation_temp'] = {
            "amount": amount,
            "purpose": purpose,
            "payment_method": payment_method
        }

        # Create Razorpay order
        order, error = create_order(
            amount,
            donor.get('first_name') + " " + donor.get('last_name')
        )

        if error:
            return render_template("donate_2.html", donor=donor, error=error)

        session['razorpay_order_id'] = order['id']

        # Render Razorpay checkout page
        return render_template(
            "razorpay_checkout.html",
            order_id=order['id'],
            amount=int(amount * 100),  # amount in paise
            key_id=os.getenv("RAZORPAY_KEY_ID"),
            donor=donor
        )

    return render_template("donate_2.html", donor=donor)


# ================= PAYMENT SUCCESS =================#
@app.route('/payment-success', methods=['POST'])
def payment_success():

    payment_id = request.form.get('razorpay_payment_id')
    order_id = request.form.get('razorpay_order_id')
    signature = request.form.get('razorpay_signature')

    # ✅ VERIFY SIGNATURE (keep your modular method)
    valid, error = verify_payment_signature(payment_id, order_id, signature)

    # 🔴 IF VERIFICATION FAILS
    if not valid:

        donor = session.get("donor_info")
        donation = session.get("donation_temp")

        if donor and donation:
            db = get_db()
            cur = db.cursor()

            cur.execute("""
                INSERT INTO donation_summary
                (user_email, donor_name, amount, status)
                VALUES (?, ?, ?, ?)
            """, (
                session.get('user'),
                donor.get('first_name') + " " + donor.get('last_name'),
                donation['amount'],
                "Failed"
            ))

            db.commit()
            db.close()

        return redirect("/payment-failed")

    donor = session.get('donor_info')
    donation = session.get('donation_temp')

    if not donor or not donation:
        return redirect('/donate')

    qr_id = "TXN" + str(random.randint(100000, 999999))
    today = date.today().strftime("%Y-%m-%d")

    db = get_db()
    cur = db.cursor()

    # ✅ Insert into DB
    cur.execute("""
        INSERT INTO donation_summary
        (user_email, donor_name, email, phone, country,
         amount, purpose, payment_method, date, qr_id, payment_id, order_id, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session.get('user'),
        donor.get('first_name') + " " + donor.get('last_name'),
        donor.get('email'),
        donor.get('phone'),
        donor.get('country'),
        donation['amount'],
        donation['purpose'],
        donation['payment_method'],
        today,
        qr_id,
        payment_id,
        order_id,
        "Paid"
    ))

    db.commit()

    # Get inserted row ID for receipt numbering
    donation_id = cur.lastrowid

    # Prepare donor data for receipt
    donor_dict = {
        "id": donation_id,
        "first_name": donor.get("first_name"),
        "last_name": donor.get("last_name"),
        "email": donor.get("email"),
        "amount": float(donation["amount"]),
        "payment_id": payment_id,
        "date": today
    }

    # ✅ Generate PDF receipt
    file_path, receipt_no = generate_receipt(donor_dict)

    db.close()

    # Clear temp session data
    session.pop('donor_info', None)
    session.pop('donation_temp', None)

    return render_template(
        "success.html",
        donor=donor_dict,
        payment_id=payment_id,
        receipt_no=receipt_no
    )

# ================= DOWNLOAD RECEIPT =================#
@app.route("/download-receipt/<receipt_no>")
def download_receipt(receipt_no):
    file_path = f"receipts/{receipt_no}.pdf"
    return send_file(file_path, as_attachment=True)

@app.route("/payment-failure", methods=["POST"])
def payment_failure():
    error = request.form.to_dict()
    print("Razorpay Failure:", error)
    return "Payment failed. Please try again.", 400



# ================= USER DASHBOARD =================#
@app.route('/user-dashboard')
def user_dashboard():
    if 'user' not in session:
        return redirect('/login')
    return render_template('user_dashboard.html')

# ================= USER DONATION =================#
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


# ================= ADMIN DASHBOARD =================#
@app.route('/admin')
def admin_dashboard():
    if 'admin' not in session:
        return redirect('/login')
    db = get_db()
    cur = db.cursor()
    # Donations
    cur.execute("SELECT COUNT(*) FROM donation_summary")
    total_donations = cur.fetchone()[0]
    cur.execute("SELECT SUM(amount) FROM donation_summary")
    total_amount = cur.fetchone()[0] or 0
    # Daily Records
    cur.execute("SELECT date, total_inmates FROM daily_records ORDER BY date DESC LIMIT 7")
    records = cur.fetchall()[::-1]
    record_dates = [r[0] for r in records]
    inmate_counts = [r[1] for r in records]
    cur.execute("SELECT COUNT(*) FROM daily_records")
    total_records = cur.fetchone()[0]
    cur.execute("SELECT SUM(total_inmates) FROM daily_records")
    total_inmates = cur.fetchone()[0] or 0
    db.close()
    return render_template('admin_dashboard.html',
                           total_donations=total_donations,
                           total_amount=total_amount,
                           record_dates=record_dates,
                           inmate_counts=inmate_counts,
                           total_records=total_records,
                           total_inmates=total_inmates)

# ================= ADMIN DONATION=================#
@app.route('/admin/donations')
def admin_donations():
    if 'admin' not in session:
        return redirect('/login')

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT donor_name, amount, purpose, payment_method, date, qr_id FROM donation_summary ORDER BY date DESC")
    rows = cur.fetchall()

    # Convert rows to list of dicts
    donations = []
    for row in rows:
        donations.append({
            "donor_name": row[0],
            "amount": row[1],
            "purpose": row[2],
            "payment_method": row[3],
            "date": row[4].strftime("%Y-%m-%d") if isinstance(row[4], (str, bytes)) == False else row[4],
            "qr_id": row[5]
        })

    db.close()
    return render_template('admin_donations.html', donations=donations)

# ================= ADMIN UPDATE =================#
@app.route('/admin/update', methods=['GET','POST'])
def admin_update():
    if 'admin' not in session:
        return redirect('/login')
    db = get_db()
    cur = db.cursor()

    if request.method == 'POST':
        cur.execute("""
        INSERT INTO daily_records
        (date, total_inmates, hospitalized, staff_count, guests_arrived)
        VALUES (?,?,?,?,?)
        """, (
            str(date.today()),
            request.form['total_inmates'],
            request.form['hospitalized'],
            request.form['staff_count'],
            request.form['guests_arrived']
        ))
        db.commit()
        db.close()
        return redirect('/admin/update')

    # Get last record for prefill
    cur.execute("SELECT * FROM daily_records ORDER BY id DESC LIMIT 1")
    record = cur.fetchone()
    # Get last 7 records for table/chart
    cur.execute("SELECT * FROM daily_records ORDER BY date DESC LIMIT 7")
    records = [dict(r) for r in cur.fetchall()]
    db.close()
    return render_template('admin_update.html', record=record, records=records)

# ================= EDIT / DELETE RECORD =================
@app.route('/admin/edit/<int:id>', methods=['GET','POST'])
def edit_record(id):
    if 'admin' not in session:
        return redirect('/login')
    db = get_db()
    cur = db.cursor()
    if request.method == 'POST':
        cur.execute("""
        UPDATE daily_records
        SET total_inmates=?, hospitalized=?, staff_count=?, guests_arrived=?
        WHERE id=?
        """, (
            request.form['total_inmates'],
            request.form['hospitalized'],
            request.form['staff_count'],
            request.form['guests_arrived'],
            id
        ))
        db.commit()
        db.close()
        return redirect('/admin/update')
    cur.execute("SELECT * FROM daily_records WHERE id=?", (id,))
    record = cur.fetchone()
    db.close()
    return render_template('edit_record.html', record=record)

@app.route('/admin/delete/<int:id>')
def delete_record(id):
    if 'admin' not in session:
        return redirect('/login')
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM daily_records WHERE id=?", (id,))
    db.commit()
    db.close()
    return redirect('/admin/update')


# ================= ADMIN RECORDS =================#
@app.route("/admin/records")
def view_records():
    if 'admin' not in session:
        return redirect('/login')

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM daily_records ORDER BY date DESC")
    records = cur.fetchall()
    conn.close()
    return render_template("view_records.html", records=records)

# ================= ADMIN - VIEW & REPLY QUESTIONS =================#
@app.route("/admin/questions", methods=["GET", "POST"])
def admin_questions():

    if "admin" not in session:
        return redirect("/login")

    db = get_db()
    cur = db.cursor()

    if request.method == "POST":
        question_id = request.form["question_id"]
        reply = request.form["reply"]

        cur.execute("""
            UPDATE questions
            SET reply = ?, status = ?
            WHERE id = ?
        """, (reply, "Replied", question_id))

        db.commit()

    cur.execute("SELECT * FROM questions ORDER BY id DESC")
    questions = cur.fetchall()
    db.close()

    return render_template("admin_questions.html", questions=questions)

# ================= SAVE VISITOR QUESTION =================#
@app.route("/ask_question", methods=["POST"])
def ask_question():

    if 'user' not in session:
        return redirect('/login')

    question = request.form["question"]
    name = session.get("user_name")
    email = session.get("user")

    db = get_db()
    cur = db.cursor()

    cur.execute("""
        INSERT INTO questions (name, email, question, status, date)
        VALUES (?, ?, ?, ?, ?)
    """, (name, email, question, "Pending", str(date.today())))

    db.commit()
    db.close()

    return redirect("/faq")

# ================= USER - VIEW MY QUESTIONS =================#
@app.route("/view-replies")
def view_replies():
    if "user" not in session:
        return redirect("/login")

    db = get_db()
    cur = db.cursor()

    # Get logged-in user's questions
    cur.execute("""
        SELECT question, reply, status
        FROM questions
        WHERE email = ?
        ORDER BY id DESC
    """, (session["user"],))

    rows = cur.fetchall()

    questions = []
    for row in rows:
        questions.append({
            "question": row[0],
            "reply": row[1],
            "status": row[2]
        })

    return render_template("my_questions.html", questions=questions)


# ================= FORGOT PASSWORD =================#
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

# ---------------- VERIFY OTP ----------------#
@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    if request.method == 'POST':
        if request.form['otp'].strip() == session.get('otp'):
            session.pop('otp')
            return redirect('/reset-password')
        return render_template('verify_otp.html', error="Invalid OTP")

    return render_template('verify_otp.html')

# ---------------- RESET PASSWORD ----------------#
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

# ================= LOGOUT =================#
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


# ================= RUN =================#
if __name__ == '__main__':
    init_db()
    app.run(debug=True)
