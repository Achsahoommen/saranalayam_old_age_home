import smtplib
from email.message import EmailMessage

def send_otp(recipient, otp):
    msg = EmailMessage()
    msg.set_content(f"Your OTP for Saranalayam password reset is: {otp}")
    msg['Subject'] = 'Saranalayam Password Reset OTP'
    msg['From'] = 'YOUR_EMAIL@gmail.com'   # replace with your email
    msg['To'] = recipient

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login('YOUR_EMAIL@gmail.com', 'YOUR_APP_PASSWORD')  # app password
            server.send_message(msg)
        print(f"OTP sent to {recipient}")
        return True
    except Exception as e:
        print("Failed to send OTP:", e)
        return False
