import os
import razorpay
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Fetch Razorpay keys from environment
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
    raise ValueError("Razorpay keys are missing! Please set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in .env")

# Initialize Razorpay client
client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


def create_order(amount, name=None, currency="INR"):
    """
    Creates a Razorpay order.
    :param amount: Amount in INR (will be converted to paise)
    :param name: Optional donor name (for notes)
    :param currency: Currency code (default INR)
    :return: tuple (order_dict, error_message). order_dict is None if error occurs
    """
    try:
        amount_paise = int(float(amount) * 100)  # Convert INR to paise
        order_data = {
            "amount": amount_paise,
            "currency": currency,
            "payment_capture": 1,  # auto-capture
        }
        if name:
            order_data["notes"] = {"name": name}

        order = client.order.create(data=order_data)
        return order, None

    except razorpay.errors.BadRequestError as e:
        return None, f"Razorpay Bad Request: {str(e)}"
    except razorpay.errors.ServerError as e:
        return None, f"Razorpay Server Error: {str(e)}"
    except Exception as e:
        return None, f"An unexpected error occurred: {str(e)}"


def verify_payment_signature(payment_id, order_id, signature):
    """
    Verifies Razorpay payment signature.
    :param payment_id: razorpay_payment_id from frontend
    :param order_id: razorpay_order_id from frontend
    :param signature: razorpay_signature from frontend
    :return: tuple (is_valid, error_message)
    """
    try:
        params = {
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature
        }
        client.utility.verify_payment_signature(params)
        return True, None
    except razorpay.errors.SignatureVerificationError:
        return False, "Payment signature verification failed!"
    except Exception as e:
        return False, f"An unexpected error occurred: {str(e)}"
