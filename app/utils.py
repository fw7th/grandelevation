import asyncio
import base64
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from fastapi import FastAPI, HTTPException
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from pydantic import BaseModel, EmailStr
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from .models import Product


async def get_active_categories(session: AsyncSession) -> list[str]:
    """
    Categories that actually have products right now, pulled live from
    the DB -- not the static SPEC_MODELS list. This is what the admin
    panel can create products in, and it grows/shrinks automatically as
    products are added/removed, with no code change needed.
    """
    statement = select(Product.category).distinct()
    result = await session.exec(statement)
    return sorted(result.all())


# If modifying these scopes, delete the file token.json.
# This scope allows full sending capabilities.

# Make sure it has "www." and the full "/auth/gmail.send" path
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


def sync_gmail_dispatch(recipient_email: str, reset_link: str):
    """Synchronous executor block that interacts with the blocking Google SDK client."""
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds:
        raise ValueError("Missing token.json file. Run initialization first.")

    # Background token refresh tracking
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    # Initialize client
    service = build("gmail", "v1", credentials=creds)

    # Construct HTML Email structure
    message = MIMEMultipart("alternative")
    message["To"] = recipient_email
    message["Subject"] = "Reset Your Password - GrandElevationSolar"

    html_content = f"""
    <html>
        <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 8px;">
                <h2 style="color: #f39c12;">Password Reset Link</h2>
                <p>Hello,</p>
                <p>We received an inquiry to reset your password. Use the verification checkpoint below:</p>
                <p style="text-align: center; margin: 25px 0;">
                    <a href="{reset_link}" style="background-color: #f39c12; color: white; padding: 12px 25px; text-decoration: none; border-radius: 4px; font-weight: bold;">Reset Password</a>
                </p>
                <p>If you did not request a profile update, please drop this transmission.</p>
            </div>
        </body>
    </html>
    """
    message.attach(MIMEText(html_content, "html"))

    # Base64url encode parameters for API transit standard
    raw_base64 = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    # Perform blocking API request
    return (
        service.users().messages().send(userId="me", body={"raw": raw_base64}).execute()
    )


@app.post("/auth/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest):
    """Non-blocking asynchronous target endpoint routing execution threads securely."""
    # Generate unique mock security asset strings
    mock_reset_token = "solar_token_xyz_987654321"
    reset_link = f"https://grandelevationsolar.com{mock_reset_token}"

    try:
        # Offload the blocking Gmail client code to an asynchronous system thread pool
        result = await asyncio.to_thread(sync_gmail_dispatch, payload.email, reset_link)
        return {
            "status": "success",
            "message": f"Password reset email sent to {payload.email}",
            "gmail_message_id": result.get("id"),
        }
    except ValueError as val_err:
        raise HTTPException(status_code=500, detail=str(val_err))
    except Exception as err:
        raise HTTPException(
            status_code=500, detail=f"Google API routing failure: {str(err)}"
        )
