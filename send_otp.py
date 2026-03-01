import smtplib
from email.message import EmailMessage

def send_otp(recipient, otp):
    sender_email = "projectmini077@gmail.com"
    app_password = "vqtzaahsqeswfbup"   # 16-digit Google App Password

    msg = EmailMessage()
    msg.set_content(f"Your OTP for Sharanstan password reset is: {otp}")
    msg['Subject'] = "Sharanstan Password Reset OTP"
    msg['From'] = sender_email
    msg['To'] = recipient

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(sender_email, app_password)
        server.send_message(msg)
        server.quit()

        print("OTP SENT SUCCESSFULLY")
        return True

    except Exception as e:
        print("SMTP ERROR:", e)
        return False