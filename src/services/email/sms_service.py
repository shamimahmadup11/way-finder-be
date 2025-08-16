# import os
# from sqlalchemy.orm import Session
# from dotenv import load_dotenv
# from twilio.rest import Client
# from src.services.otp_generation.otp_service import otp_service
# import logging

# load_dotenv()
# logger = logging.getLogger(__name__)

# def send_phone_verification_otp(phone_number : str, phone_country_code: str, db: Session):

#     """Send an SMS with OTP for verification"""
#     # Generate OTP for this phone number
#     # otp = otp_service.generate_otp(phone_number)
#     otp = otp_service.generate_otp(phone_number, 'phone', db)

#     phone_number_code = f"{phone_country_code}{phone_number}"
    
#     # Twilio credentials
#     account_sid = os.getenv('TWILIO_ACCOUNT_SID')
#     auth_token = os.getenv('TWILIO_AUTH_TOKEN')
#     from_number = os.getenv('TWILIO_PHONE_NUMBER')
    
#     if not all([account_sid, auth_token, from_number]):
#         logger.error("Twilio credentials not properly configured")
#         return {
#             "status": "error",
#             "message": "SMS service not properly configured"
#         }
    
#     try:
#         client = Client(account_sid, auth_token)
#         message = client.messages.create(
#             body=f"Your xPi verification code is: {otp}. This code will expire in 15 minutes.",
#             from_=from_number,
#             to=phone_number_code
#         )
        
#         return {
#             "status": "success",
#             "message": "Verification SMS sent successfully",
#             "sid": message.sid
#         }
#     except Exception as e:
#         logger.error(f"Failed to send SMS: {str(e)}")
#         return {
#             "status": "error",
#             "message": f"Failed to send verification SMS: {str(e)}"
#         }



import os
import resend
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from src.services.otp_generation.otp_service import otp_service
import logging

load_dotenv()
logger = logging.getLogger(__name__)

resend.api_key = os.getenv("RESEND_API_KEY")

def send_phone_verification_otp(phone_number: str, phone_country_code: str, db: Session, email: str):
    """Send OTP to user's email instead of SMS using Resend"""
    try:
        # Generate OTP
        otp = otp_service.generate_otp(phone_number, 'phone', db)

        # Email body
        subject = "Your xPi Phone Verification Code"
        html_content = f"""
        <h1>Phone Verification</h1>
        <p>Your verification code is:</p>
        <h2 style="letter-spacing: 5px;">{otp}</h2>
        <p>This code will expire in 15 minutes.</p>
        """

        # Send via Resend
        params = {
            "from": os.getenv("FROM_EMAIL"),
            "to": email,
            "subject": subject,
            "html": html_content
        }
        resend.Emails.send(params)

        return {
            "status": "success",
            "message": f"OTP sent to {email} instead of SMS"
        }

    except Exception as e:
        logger.error(f"Failed to send OTP via Resend: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to send OTP: {str(e)}"
        }