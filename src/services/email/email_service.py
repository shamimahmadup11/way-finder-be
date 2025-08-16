
import os
import resend
from dotenv import load_dotenv
from src.services.otp_generation.otp_service import otp_service
from sqlalchemy.ext.asyncio import AsyncSession
import logging

load_dotenv()
logger = logging.getLogger(__name__)

# Set Resend API key
resend.api_key = os.getenv("RESEND_API_KEY")


def welcome_email(to_email: str):
    """Send a welcome email using Resend"""
    from_email = os.getenv("FROM_EMAIL")

    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Welcome to xPi</title>
    </head>
    <body style="font-family: Arial, sans-serif; background-color: #f4f4f9; color: #333;">
        <div style="max-width:600px; margin:auto; background-color:#fff; padding:20px; border-radius:8px;">
            <div style="background-color:#f97316; color:white; padding:20px; text-align:center; border-radius:8px 8px 0 0;">
                <h1>Welcome to xPi!</h1>
            </div>
            <div style="padding:20px;">
                <h2 style="color:#2c3e50;">Welcome Aboard!</h2>
                <p>Dear <strong>User</strong>,</p>
                <p>We're excited to have you join xPi! Your journey with us starts now, and we're here to assist every step of the way.</p>
                <p><strong>Welcome to the xPi family!</strong></p>
                <p>Best regards,<br>The xPi Team</p>
            </div>
        </div>
    </body>
    </html>
    """

    try:
        resend.Emails.send({
            "from": from_email,
            "to": to_email,
            "subject": "Welcome to xPi",
            "html": html_content
        })
        return {"status": "success", "message": "Welcome email sent"}
    except Exception as e:
        logger.error(f"Failed to send welcome email: {str(e)}")
        return {"status": "error", "message": str(e)}


async def send_email_verification_otp(to_email: str, db: AsyncSession):
    """Send an OTP email using Resend"""
    from_email = os.getenv("FROM_EMAIL")
    otp = await otp_service.generate_otp(to_email, "email", db)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Email Verification - xPi</title>
    </head>
    <body style="font-family: Arial, sans-serif; background-color: #f4f4f9; color: #333;">
        <div style="max-width:600px; margin:auto; background-color:#fff; padding:20px; border-radius:8px;">
            <div style="background-color:#f97316; color:white; padding:20px; text-align:center; border-radius:8px 8px 0 0;">
                <h1>Email Verification</h1>
            </div>
            <div style="padding:20px;">
                <p>Dear User,</p>
                <p>Your verification code is:</p>
                <div style="padding:15px; background-color:#f0f0f0; text-align:center; font-size:24px; letter-spacing:5px; font-weight:bold;">
                    {otp}
                </div>
                <p>This code will expire in 15 minutes.</p>
            </div>
        </div>
    </body>
    </html>
    """

    try:
        params: resend.Emails.SendParams = {
    "from": "Acme <onboarding@resend.dev>",
    "to": ["delivered@resend.dev"],
    "subject": "hello world",
    "html": "<strong>it works!</strong>",
}      
        email = resend.Emails.send(params)
        print(email)
        return {"status": "success", "message": "Verification email sent"}
    except Exception as e:
        return {"status": "error", "message": f"Failed to send: {str(e)}"}


def send_password_reset_email(to_email: str, reset_token: str):
    """Send password reset email using Resend"""
    from_email = os.getenv("FROM_EMAIL")
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    reset_link = f"{frontend_url}/reset_password?token={reset_token}"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Password Reset - xPi</title>
    </head>
    <body style="font-family: Arial, sans-serif; background-color: #f4f4f9; color: #333;">
        <div style="max-width:600px; margin:auto; background-color:#fff; padding:20px; border-radius:8px;">
            <div style="background-color:#f97316; color:white; padding:20px; text-align:center; border-radius:8px 8px 0 0;">
                <h1>Password Reset</h1>
            </div>
            <div style="padding:20px;">
                <p>Dear User,</p>
                <p>Click the button below to reset your password:</p>
                <p style="text-align:center;">
                    <a href="{reset_link}" style="display:inline-block; padding:10px 20px; background-color:#4F47E4; color:white; text-decoration:none; border-radius:5px;">Reset Password</a>
                </p>
                <p>This link will expire in 24 hours.</p>
            </div>
        </div>
    </body>
    </html>
    """

    try:
        resend.Emails.send({
            "from": from_email,
            "to": to_email,
            "subject": "Reset Your Password - Digital Signage",
            "html": html_content
        })
        return {"status": "success", "message": "Password reset email sent"}
    except Exception as e:
        return {"status": "error", "message": f"Failed to send: {str(e)}"}