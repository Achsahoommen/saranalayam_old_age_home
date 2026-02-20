# ================= FLASK CORE =================
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    jsonify,
    send_file,
    url_for
)
# ================= STANDARD LIBRARY =================
import os
import io
import sqlite3
import random
import csv
from datetime import date, datetime
from io import StringIO, BytesIO
from datetime import date, datetime
from functools import wraps
# ================= SECURITY & UPLOADS =================
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
# ================= AUTH DECORATORS =================
from decorators import admin_required
# ================= OTP =================
from send_otp import send_otp
# ================= RAZORPAY =================
import razorpay
from razorpay_utils import (
    client as razorpay_client,
    RAZORPAY_KEY_ID,
    create_order,
    verify_payment_signature
)
# ================= RECEIPTS =================
from receipt_utils import generate_receipt
# ================= REPORTLAB (PDF EXPORTS) =================
from calendar import calendar
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    PageBreak
)
from reportlab.graphics.shapes import Drawing, String
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.charts.barcharts import VerticalBarChart

def build_trend_chart(data, title):
    drawing = Drawing(460, 220)

    drawing.add(String(
        230, 195, title,
        textAnchor="middle",
        fontSize=11,
        fontName="Helvetica-Bold"
    ))

    chart = LinePlot()
    chart.x = 40
    chart.y = 40
    chart.width = 380
    chart.height = 130

    chart.data = [[(i + 1, v) for i, v in enumerate(data)]]
    chart.lines[0].strokeColor = colors.HexColor("#2563eb")
    chart.lines[0].strokeWidth = 2

    chart.yValueAxis.valueMin = 0
    chart.yValueAxis.visibleGrid = True
    chart.yValueAxis.gridStrokeColor = colors.lightgrey

    chart.xValueAxis.visibleTicks = False
    chart.xValueAxis.visibleLabels = False

    drawing.add(chart)
    return drawing

app = Flask(__name__)
app.secret_key = "saranalayam_secret_key_2026"
app.config['UPLOAD_FOLDER'] = 'static/uploads'

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
DB = 'saranalayam.db'

# ================= DATABASE CONNECTION ================= #
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn
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
        except sqlite3.IntegrityError:
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
    cur.execute("SELECT date, total_inmates FROM daily_records ORDER BY date DESC LIMIT 30")
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

# ==================== ADMIN UPDATE =======================#
@app.route('/admin/update', methods=['GET', 'POST'])
def admin_update():
    if 'admin' not in session:
        return redirect('/login')

    db = get_db()
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    # ================= POST =================
    if request.method == 'POST':

        # ==== CAPTURE FORM DATA ====
        hospitalized_data = request.form.get('hospitalized_names', '').strip()
        discharged_data = request.form.get('discharged_names', '').strip()
        deceased_data = request.form.get('deceased_names', '').strip()

        new_inmates = int(request.form.get('new_inmates', 0))
        staff_count = int(request.form.get('staff_count', 0))
        guests_arrived = int(request.form.get('guests_visited', 0))

        # ================= UPDATE HOSPITALIZED =================
        if hospitalized_data:
            parts = hospitalized_data.split("||")

            names = [n.strip() for n in parts[0].split(",") if n.strip()]
            hospital = parts[1] if len(parts) > 1 else None

            for name in names:
                cur.execute("""
                    UPDATE inmates
                    SET status = 'Hospitalized',
                        hospital_details = ?,
                        previous_status = 'Active',
                        status_updated_date = ?,
                        date_of_death = NULL
                    WHERE name = ? AND status = 'Active'
                """, (
                    hospital,
                    str(date.today()),
                    name
                ))

        # ================= UPDATE DISCHARGED =================
        if discharged_data:
            names_list = [n.strip() for n in discharged_data.split(",") if n.strip()]

            for name in names_list:
                cur.execute("""
                    UPDATE inmates
                    SET status = 'Discharged',
                        hospital_details = NULL,
                        previous_status = status,
                        status_updated_date = ?,
                        date_of_death = NULL
                    WHERE name = ? AND status IN ('Active','Hospitalized')
                """, (
                    str(date.today()),
                    name
                ))

        # ================= UPDATE DECEASED =================
        if deceased_data:
            names_list = [n.strip() for n in deceased_data.split(",") if n.strip()]

            for name in names_list:
                cur.execute("""
                    UPDATE inmates
                    SET status = 'Deceased',
                        hospital_details = NULL,
                        previous_status = status,
                        status_updated_date = ?,
                        date_of_death = ?
                    WHERE name = ? AND status != 'Deceased'
                """, (
                    str(date.today()),
                    str(date.today()),
                    name
                ))

        db.commit()

        # ================= AUTO CALCULATE COUNTS =================

        cur.execute("SELECT COUNT(*) FROM inmates WHERE status != 'Deceased'")
        total = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM inmates WHERE status='Hospitalized'")
        hospitalized_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM inmates WHERE status='Discharged'")
        discharged_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM inmates WHERE status='Deceased'")
        deceased_count = cur.fetchone()[0]

        active = total - hospitalized_count - discharged_count

        cur.execute("SELECT COUNT(*) FROM inmates WHERE gender='Male' AND status='Active'")
        male = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM inmates WHERE gender='Female' AND status='Active'")
        female = cur.fetchone()[0]

        # ================= SAVE DAILY SNAPSHOT =================
        cur.execute("""
            INSERT OR REPLACE INTO daily_records
            (date, total_inmates, active_inmates, male_inmates, female_inmates,
             new_inmates, discharged, hospitalized, deceased,
             staff_count, guests_arrived)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(date.today()),
            total,
            active,
            male,
            female,
            new_inmates,
            discharged_count,
            hospitalized_count,
            deceased_count,
            staff_count,
            guests_arrived
        ))

        db.commit()
        db.close()

        return redirect('/admin/update')

    # ================= GET =================

    cur.execute("SELECT COUNT(*) FROM inmates WHERE status != 'Deceased'")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM inmates WHERE status='Hospitalized'")
    hospitalized = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM inmates WHERE status='Discharged'")
    discharged = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM inmates WHERE status='Deceased'")
    deceased = cur.fetchone()[0]

    active = total - hospitalized - discharged

    cur.execute("SELECT COUNT(*) FROM inmates WHERE gender='Male' AND status='Active'")
    male = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM inmates WHERE gender='Female' AND status='Active'")
    female = cur.fetchone()[0]

    cur.execute("SELECT * FROM daily_records ORDER BY date DESC LIMIT 7")
    records = [dict(row) for row in cur.fetchall()]

    db.close()

    return render_template(
        'admin_update.html',
        records=records,
        total=total,
        active=active,
        male=male,
        female=female,
        hospitalized=hospitalized,
        discharged=discharged,
        deceased=deceased
    )

#===================== INMATES ========================#
@app.route("/admin/inmates")
def view_inmates():
    if "admin" not in session:
        return redirect("/")

    db = get_db()
    inmates = db.execute(
        "SELECT * FROM inmates ORDER BY admission_date DESC"
    ).fetchall()

    return render_template("inmates.html", inmates=inmates)

@app.route("/admin/export/inmates/csv")
def export_inmates_csv():

    # 🔐 Admin protection
    if "admin" not in session:
        return redirect("/login")

    # 📅 Date filters
    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")

    query = "SELECT * FROM inmates WHERE 1=1"
    params = []

    if from_date:
        query += " AND admission_date >= ?"
        params.append(from_date)

    if to_date:
        query += " AND admission_date <= ?"
        params.append(to_date)

    query += " ORDER BY admission_date DESC"

    db = get_db()
    inmates = db.execute(query, params).fetchall()
    db.close()

    # 📝 Create CSV
    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Name", "Age", "Gender", "Admission Date",
        "Status", "Illness", "Hospital", "Notes"
    ])

    for i in inmates:
        writer.writerow([
            i["name"],
            i["age"],
            i["gender"],
            i["admission_date"],
            i["status"],
            i["illness"],
            i["hospital_details"],
            i["notes"]
        ])

    response = app.response_class(
        output.getvalue(),
        mimetype="text/csv"
    )
    response.headers["Content-Disposition"] = "attachment; filename=inmates.csv"

    return response
#===================== REPORTS(MONTHLY & YEARLY) ========================#
#==============MONTHY REPORT PDF EXPORT==============#
@app.route("/admin/export/monthly-report/pdf")
@admin_required
def export_monthly_report_pdf():

    # ===== MONTH =====
    month = request.args.get("month") or datetime.now().strftime("%Y-%m")

    year, mon = map(int, month.split("-"))
    last_day = calendar.monthrange(year, mon)[1]

    start_date = f"{month}-01"
    end_date = f"{month}-{last_day}"

    conn = sqlite3.connect("saranalayam.db")
    cursor = conn.cursor()

    # ===== SUMMARY + AVERAGE AGE =====
    cursor.execute("""
        SELECT
            COUNT(*),
            SUM(CASE WHEN status='Active' THEN 1 ELSE 0 END),
            SUM(CASE WHEN status='Hospitalized' THEN 1 ELSE 0 END),
            SUM(CASE WHEN status='Discharged' THEN 1 ELSE 0 END),
            SUM(CASE WHEN status='Deceased' THEN 1 ELSE 0 END),
            AVG(age)
        FROM inmates
    """)
    total, active, hosp, disch, dead, avg_age = cursor.fetchone()

    active = active or 0
    hosp = hosp or 0
    disch = disch or 0
    dead = dead or 0
    avg_age = round(avg_age, 1) if avg_age else 0

    # ===== GENDER STATS =====
    cursor.execute("""
        SELECT gender, COUNT(*)
        FROM inmates
        GROUP BY gender
    """)
    gender_rows = cursor.fetchall()

    male = female = others = 0
    for g, count in gender_rows:
        if g.lower() == "male":
            male = count
        elif g.lower() == "female":
            female = count
        else:
            others = count

    # ===== DAILY RECORDS =====
    cursor.execute("""
        SELECT date, total_inmates, active_inmates, hospitalized,
               discharged, deceased, new_inmates, staff_count, guests_arrived
        FROM daily_records
        WHERE date BETWEEN ? AND ?
        ORDER BY date
    """, (start_date, end_date))
    daily = cursor.fetchall()

    # ===== FULL INMATE LIST =====
    cursor.execute("""
        SELECT name, age, gender, status
        FROM inmates
        ORDER BY name
    """)
    inmates = cursor.fetchall()

    conn.close()

    # ===== PDF SETUP =====
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    elements = []

    # ===== TITLE =====
    elements.append(Paragraph("<b>SARANALAYAM OLD AGE HOME</b>", styles["Title"]))
    elements.append(Paragraph("<b>Monthly Inmate Analytics Report</b>", styles["Heading2"]))
    elements.append(Paragraph(f"<b>Month:</b> {month}", styles["Normal"]))
    elements.append(Paragraph(
        f"<b>Generated on:</b> {datetime.now().strftime('%d %B %Y')}",
        styles["Normal"]
    ))
    elements.append(Spacer(1, 16))

    # ===== SUMMARY TABLE =====
    summary = Table([
        ["Metric", "Count"],
        ["Total Inmates", total],
        ["Active", active],
        ["Hospitalized", hosp],
        ["Discharged", disch],
        ["Deceased", dead],
        ["Average Age", avg_age],
        ["Male", male],
        ["Female", female],
        ["Others", others],
    ], colWidths=[260, 100])

    summary.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.4, colors.grey),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#2563eb")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (1,1), (-1,-1), 'CENTER')
    ]))

    elements.append(summary)
    elements.append(Spacer(1, 20))

    # ===== STATUS CHART =====
    elements.append(Paragraph("<b>Status Distribution</b>", styles["Heading2"]))
    elements.append(Spacer(1, 10))

    chart = VerticalBarChart()
    chart.data = [[active, hosp, disch, dead]]
    chart.categoryAxis.categoryNames = ["Active", "Hospitalized", "Discharged", "Deceased"]
    chart.width = 400
    chart.height = 220
    chart.barWidth = 30
    chart.valueAxis.valueMin = 0

    drawing = Drawing(450, 250)
    drawing.add(chart)
    elements.append(drawing)

    # ===== DAILY RECORDS =====
    elements.append(PageBreak())
    elements.append(Paragraph("<b>Daily Records</b>", styles["Heading2"]))
    elements.append(Spacer(1, 10))

    daily_table = [
        ["Date","Total","Active","Hosp","Disch","Dead","New","Staff","Guests"]
    ]

    for d in daily:
        daily_table.append([d[0], d[1], d[2], d[3], d[4], d[5], d[6], d[7], d[8]])

    daily_tbl = Table(daily_table, repeatRows=1)
    daily_tbl.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#16a34a")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('ALIGN', (1,1), (-1,-1), 'CENTER')
    ]))

    elements.append(daily_tbl)

    # ===== INMATE LIST =====
    elements.append(PageBreak())
    elements.append(Paragraph("<b>Inmate List</b>", styles["Heading2"]))
    elements.append(Spacer(1, 10))

    inmate_table = [["Name", "Age", "Gender", "Status"]]
    for i in inmates:
        inmate_table.append(list(i))

    inmates_tbl = Table(
        inmate_table,
        colWidths=[220, 50, 80, 90],
        repeatRows=1
    )

    inmates_tbl.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0f766e")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('ALIGN', (1,1), (-1,-1), 'CENTER')
    ]))

    elements.append(inmates_tbl)

    # ===== FOOTER =====
    def footer(canvas, doc):
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(
            A4[0] - 36,
            20,
            f"Page {doc.page} | Saranalayam Admin System"
        )

    doc.build(elements, onFirstPage=footer, onLaterPages=footer)

    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"monthly_report_{month}.pdf",
        mimetype="application/pdf"
        
    )
#==============YEARLY REPORT PDF EXPORT==============#
@app.route("/admin/export/yearly-report/pdf")
@admin_required
def export_yearly_report_pdf():

    year = request.args.get("year") or datetime.now().strftime("%Y")
    start = f"{year}-01-01"
    end = f"{year}-12-31"

    conn = sqlite3.connect("saranalayam.db")
    cursor = conn.cursor()

    # ===== SUMMARY =====
    cursor.execute("""
        SELECT
            COUNT(*),
            SUM(CASE WHEN status='Active' THEN 1 ELSE 0 END),
            SUM(CASE WHEN status='Hospitalized' THEN 1 ELSE 0 END),
            SUM(CASE WHEN status='Discharged' THEN 1 ELSE 0 END),
            SUM(CASE WHEN status='Deceased' THEN 1 ELSE 0 END),
            AVG(age)
        FROM inmates
    """)
    total, active, hosp, disch, dead, avg_age = cursor.fetchone()

    active = active or 0
    hosp = hosp or 0
    disch = disch or 0
    dead = dead or 0
    avg_age = round(avg_age, 1) if avg_age else 0

    # ===== GENDER STATS =====
    cursor.execute("""
        SELECT gender, COUNT(*)
        FROM inmates
        GROUP BY gender
    """)
    gender_rows = cursor.fetchall()

    male = female = others = 0
    for g, count in gender_rows:
        if g.lower() == "male":
            male = count
        elif g.lower() == "female":
            female = count
        else:
            others = count

    # ===== MONTHLY TOTALS =====
    cursor.execute("""
        SELECT substr(admission_date,1,7) AS month,
               COUNT(*)
        FROM inmates
        WHERE admission_date BETWEEN ? AND ?
        GROUP BY month
        ORDER BY month
    """, (start, end))
    monthly = cursor.fetchall()

    # ===== DAILY TRENDS =====
    def trend(days, column):
        cursor.execute(f"""
            SELECT {column}
            FROM daily_records
            WHERE date BETWEEN ? AND ?
            ORDER BY date DESC
            LIMIT ?
        """, (start, end, days))
        rows = cursor.fetchall()
        return [r[0] for r in rows][::-1] if rows else []

    active_30 = trend(30, "active_inmates")
    active_90 = trend(90, "active_inmates")
    hosp_30 = trend(30, "hospitalized")
    dead_30 = trend(30, "deceased")

    # ===== INMATES LIST =====
    cursor.execute("""
        SELECT id, name, age, admission_date, status
        FROM inmates
        WHERE admission_date BETWEEN ? AND ?
        ORDER BY admission_date
    """, (start, end))
    inmates_list = cursor.fetchall()

    conn.close()

    # ===== PDF SETUP =====
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=36, leftMargin=36,
                            topMargin=36, bottomMargin=36)

    styles = getSampleStyleSheet()
    elements = []

    # ===== TITLE =====
    elements.append(Paragraph("<b>SARANALAYAM OLD AGE HOME</b>", styles["Title"]))
    elements.append(Paragraph(f"<b>Yearly Consolidated Report – {year}</b>", styles["Heading2"]))
    elements.append(Spacer(1, 16))

    # ===== SUMMARY TABLE =====
    summary = Table([
        ["Metric", "Count"],
        ["Total Inmates", total],
        ["Active", active],
        ["Hospitalized", hosp],
        ["Discharged", disch],
        ["Deceased", dead],
        ["Average Age", avg_age]
    ], colWidths=[260, 100])

    summary.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.4, colors.grey),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#2563eb")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (1,1), (-1,-1), 'CENTER')
    ]))
    elements.append(summary)

    # ===== GENDER TABLE =====
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("<b>Gender Statistics</b>", styles["Heading2"]))
    elements.append(Spacer(1, 10))

    gender_table = Table([
        ["Gender", "Count"],
        ["Male", male],
        ["Female", female],
        ["Others", others]
    ], colWidths=[260, 100])

    gender_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.4, colors.grey),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#9333ea")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (1,1), (-1,-1), 'CENTER')
    ]))

    elements.append(gender_table)
    elements.append(PageBreak())

    # ===== MONTHLY TABLE =====
    elements.append(Paragraph("<b>Monthly Admissions</b>", styles["Heading2"]))
    elements.append(Spacer(1, 10))
    month_table = [["Month", "Admissions"]] + (monthly if monthly else [["—", 0]])
    mt = Table(month_table, repeatRows=1)
    mt.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#16a34a")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (1,1), (-1,-1), 'CENTER')
    ]))
    elements.append(mt)
    elements.append(PageBreak())

    # ===== INMATES LIST TABLE =====
    elements.append(Paragraph("<b>List of Inmates Admitted</b>", styles["Heading2"]))
    elements.append(Spacer(1, 10))

    if inmates_list:
        inmate_table_data = [["ID", "Name", "Age", "Admission Date", "Status"]] + inmates_list
        it = Table(inmate_table_data, repeatRows=1, colWidths=[40, 150, 40, 100, 100])
        it.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f59e0b")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (2,1), (2,-1), 'CENTER'),
            ('ALIGN', (3,1), (3,-1), 'CENTER'),
            ('ALIGN', (4,1), (4,-1), 'CENTER'),
        ]))
        elements.append(it)
    else:
        elements.append(Paragraph("<i>No inmates admitted during this year.</i>", styles["Normal"]))

    elements.append(PageBreak())

    # ===== TREND CHARTS =====
    elements.append(Paragraph("<b>Trend Analysis</b>", styles["Heading2"]))
    elements.append(Spacer(1, 12))
    if active_30:
        elements.append(build_trend_chart(active_30, "Active – Last 30 Days"))
        elements.append(Spacer(1, 14))
    if active_90:
        elements.append(build_trend_chart(active_90, "Active – Last 90 Days"))
        elements.append(Spacer(1, 14))
    if hosp_30:
        elements.append(build_trend_chart(hosp_30, "Hospitalized – Last 30 Days"))
        elements.append(Spacer(1, 14))
    if dead_30:
        elements.append(build_trend_chart(dead_30, "Deceased – Last 30 Days"))
    if not any([active_30, active_90, hosp_30, dead_30]):
        elements.append(Paragraph("<i>No daily tracking data available for this year.</i>", styles["Normal"]))

    # ===== FOOTER =====
    def footer(canvas, doc):
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(A4[0] - 36, 20, f"Page {doc.page} | Saranalayam Admin System")

    doc.build(elements, onFirstPage=footer, onLaterPages=footer)

    buffer.seek(0)
    return send_file(buffer,
                     as_attachment=True,
                     download_name=f"yearly_report_{year}.pdf",
                     mimetype="application/pdf")

#===============ADMIN ADD INMATE =================#
@app.route("/admin/inmates/add", methods=["GET", "POST"])
def add_inmate():
    if "admin" not in session:
        return redirect("/")

    if request.method == "POST":
        db = get_db()
        db.execute("""
            INSERT INTO inmates
            (name, age, gender, admission_date,status,illness, hospital_details, notes,date_of_death)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?,?)
        """, (
            request.form["name"],
            request.form["age"],
            request.form["gender"],
            request.form["admission_date"],
            request.form["status"],
            request.form["illness"],
            request.form["hospital_details"],
            request.form["notes"],
            request.form.get("date_of_death")
        ))
        db.commit()
        return redirect("/admin/inmates")

    return render_template("add_inmate.html")

#=============ADMIN EDIT INMATES =================#
@app.route("/admin/edit-inmate/<int:id>", methods=["GET", "POST"])
def edit_inmate(id):
    if "admin" not in session:   
        return redirect("/login")
    
    db = get_db()
    cur = db.cursor()

    if request.method == "POST":
        cur.execute("""
            UPDATE inmates SET
            name=?,
            age=?,
            gender=?,
            admission_date=?,
            status=?,
            illness=?,
            hospital_details=?,
            notes=?,
            date_of_death=?
            WHERE id=?
        """, (
            request.form["name"],
            request.form["age"],
            request.form["gender"],
            request.form["admission_date"],
            request.form["status"],
            request.form["illness"],
            request.form["hospital_details"],
            request.form["notes"],
            request.form.get("date_of_death"),  
            id
        ))

        db.commit()
        return redirect("/admin/inmates")

    cur.execute("SELECT * FROM inmates WHERE id=?", (id,))
    inmate = cur.fetchone()

    return render_template("edit_inmate.html", inmate=inmate)

#=================== ADMIN ANALYTICS =================#
@app.route("/admin/analytics")
def analytics_dashboard():
    if "admin" not in session:
        return redirect("/")

    db = get_db()
    db.row_factory = sqlite3.Row

    # ===== CURRENT LIVE COUNTS =====
    total_active = db.execute(
        "SELECT COUNT(*) FROM inmates WHERE status='Active'"
    ).fetchone()[0]

    male = db.execute(
        "SELECT COUNT(*) FROM inmates WHERE gender='Male' AND status='Active'"
    ).fetchone()[0]

    female = db.execute(
        "SELECT COUNT(*) FROM inmates WHERE gender='Female' AND status='Active'"
    ).fetchone()[0]

    hospitalized = db.execute(
        "SELECT COUNT(*) FROM inmates WHERE status='Hospitalized'"
    ).fetchone()[0]

    discharged = db.execute(
        "SELECT COUNT(*) FROM inmates WHERE status='Discharged'"
    ).fetchone()[0]

    deceased = db.execute(
        "SELECT COUNT(*) FROM inmates WHERE status='Deceased'"
    ).fetchone()[0]

    # ===== FETCH LAST 90 DAYS DATA =====
    rows = db.execute("""
        SELECT date,
               total_inmates,
               active_inmates,
               new_inmates,
               discharged,
               hospitalized,
               deceased
        FROM daily_records
        ORDER BY date DESC
        LIMIT 90
    """).fetchall()

    # Convert Row objects to dictionaries
    records = [dict(row) for row in rows]

    db.close()

    return render_template(
        "analytics.html",
        total_active=total_active,
        male=male,
        female=female,
        hospitalized=hospitalized,
        discharged=discharged,
        deceased=deceased,
        records=records
    )

# ================= ADMIN EDIT DAILY RECORD =================
@app.route("/admin/edit/<int:id>", methods=["GET", "POST"])
def admin_edit(id):

    if "admin" not in session:
        return redirect("/login")

    db = get_db()
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    # ===== UPDATE MODE =====
    if request.method == "POST":

        total_inmates = int(request.form['total_inmates'])
        active_inmates = int(request.form['active_inmates'])
        male_inmates = int(request.form['male_inmates'])
        female_inmates = int(request.form['female_inmates'])
        new_inmates = int(request.form['new_inmates'])
        hospitalized = int(request.form['hospitalized'])
        discharged = int(request.form['discharged'])
        deceased = int(request.form['deceased'])
        staff_count = int(request.form['staff_count'])
        guests_arrived = int(request.form['guests_arrived'])

        cur.execute("""
            UPDATE daily_records SET
                total_inmates=?,
                active_inmates=?,
                male_inmates=?,
                female_inmates=?,
                new_inmates=?,
                hospitalized=?,
                discharged=?,
                deceased=?,
                staff_count=?,
                guests_arrived=?
            WHERE id=?
        """, (
            total_inmates,
            active_inmates,
            male_inmates,
            female_inmates,
            new_inmates,
            hospitalized,
            discharged,
            deceased,
            staff_count,
            guests_arrived,
            id
        ))

        db.commit()
        db.close()

        return redirect("/admin/update")

    # ===== GET RECORD =====
    cur.execute("SELECT * FROM daily_records WHERE id=?", (id,))
    row = cur.fetchone()

    if not row:
        db.close()
        return redirect("/admin/update")

    record = dict(row)

    db.close()

    return render_template("admin_edit_record.html", record=record)

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
    db.close()
    return render_template("my_questions.html", questions=questions)

# ================= BLOG ROUTES =================#

# 1. PUBLIC BLOG FEED
@app.route('/blog')
def blog_index():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM blog_posts ORDER BY id DESC")
    posts = cur.fetchall()
    db.close()
    return render_template('blog.html', posts=posts)

# 2. VIEW SINGLE POST
@app.route('/blog/<int:post_id>')
def view_post(post_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM blog_posts WHERE id = ?", (post_id,))
    post = cur.fetchone()
    db.close()
    if post is None:
        return "Post not found", 404
    return render_template('view_post.html', post=post)

# 3. ADMIN BLOG MANAGEMENT (Add & Edit)
@app.route('/admin/add-blog', methods=['GET', 'POST'])
def add_blog():
    if 'admin' not in session:
        return redirect('/login')

    db = get_db()
    cur = db.cursor()

    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        author = session.get('admin')
        today = date.today().strftime("%B %d, %Y")
        
        file = request.files.get('image')
        filename = request.form.get('old_image')
        
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        post_id = request.form.get('post_id')
        if post_id: # Update existing
            cur.execute("UPDATE blog_posts SET title=?, content=?, image_filename=? WHERE id=?", 
                       (title, content, filename, post_id))
        else: # Insert new
            cur.execute("INSERT INTO blog_posts (title, content, image_filename, date_posted) VALUES (?,?,?,?)",
                       (title, content, filename, today))
        
        db.commit()
        return redirect('/admin/add-blog')

    cur.execute("SELECT * FROM blog_posts ORDER BY id DESC")
    posts = cur.fetchall()
    db.close()
    return render_template('admin_add_blog.html', posts=posts, edit_post=None)

# 4. FETCH POST FOR EDITING
@app.route('/admin/edit-blog/<int:id>')
def edit_blog(id):
    if 'admin' not in session:
        return redirect('/login')
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM blog_posts WHERE id=?", (id,))
    post = cur.fetchone()
    cur.execute("SELECT * FROM blog_posts ORDER BY id DESC")
    all_posts = cur.fetchall()
    db.close()
    return render_template('admin_add_blog.html', posts=all_posts, edit_post=post)

# 5. DELETE POST
@app.route('/admin/delete-blog/<int:id>')
def delete_blog(id):
    if 'admin' not in session:
        return redirect('/login')
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM blog_posts WHERE id=?", (id,))
    db.commit()
    db.close()
    return redirect('/admin/add-blog')

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

#===================== RESET PASSWORD ========================#
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

# ===================== LOGOUT ========================#
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ======================= RUN ========================#
if __name__ == '__main__':
    app.run(debug=True)