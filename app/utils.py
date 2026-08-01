import asyncio
import base64
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from fastapi import Request
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from .models import Product, Session, Users


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
    <body style="margin:0; padding:0; background-color:#FAF8F3;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#FAF8F3;">
        <tr>
          <td align="center" style="padding:48px 20px;">
            <table role="presentation" width="100%" max-width="480" cellspacing="0" cellpadding="0" border="0" style="max-width:480px; width:100%; background:#ffffff; border-radius:20px; border:1px solid rgba(10,10,10,0.08); overflow:hidden;">
              
              <!-- Header -->
              <tr>
                <td style="padding:36px 36px 24px; text-align:center; border-bottom:1px solid rgba(10,10,10,0.06);">
                  <img src="https://grandelevationsolar.com/grand-logo.png" alt="Grand Elevation Solar" width="42" height="42" style="border-radius:50%; display:block; margin:0 auto 14px;">
                  <h1 style="margin:0; font-family:'Sora', Arial, Helvetica, sans-serif; font-size:20px; font-weight:700; color:#0A0A0A; letter-spacing:-0.01em;">Reset your password</h1>
                </td>
              </tr>

              <!-- Body -->
              <tr>
                <td style="padding:32px 36px;">
                  <p style="margin:0 0 16px; font-family:'Inter', Arial, Helvetica, sans-serif; font-size:15px; color:#444; line-height:1.6;">
                    We received a request to reset the password for your account. Click the button below to choose a new one.
                  </p>
                  
                  <p style="margin:0 0 28px; font-family:'Inter', Arial, Helvetica, sans-serif; font-size:15px; color:#444; line-height:1.6;">
                    This link expires in <strong style="color:#0A0A0A;">1 hour</strong> and can only be used once.
                  </p>

                  <!-- CTA -->
                  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                    <tr>
                      <td align="center" style="padding:0 0 28px;">
                        <a href="{reset_link}" style="display:inline-block; background-color:#0A0A0A; color:#FAF8F3; font-family:'Inter', Arial, Helvetica, sans-serif; font-size:15px; font-weight:600; text-decoration:none; padding:14px 32px; border-radius:999px;">
                          Reset password
                        </a>
                      </td>
                    </tr>
                  </table>

                  <p style="margin:0 0 12px; font-family:'Inter', Arial, Helvetica, sans-serif; font-size:13px; color:#6B6B6B; line-height:1.5;">
                    If the button doesn't work, paste this link into your browser:
                  </p>
                  <p style="margin:0; font-family:'Inter', Arial, Helvetica, sans-serif; font-size:12px; color:#6B6B6B; line-height:1.5; word-break:break-all;">
                    <a href="{reset_link}" style="color:#E8651C; text-decoration:underline;">{reset_link}</a>
                  </p>
                </td>
              </tr>

              <!-- Footer -->
              <tr>
                <td style="padding:24px 36px; background:#FAF8F3; text-align:center; border-top:1px solid rgba(10,10,10,0.06);">
                  <p style="margin:0 0 6px; font-family:'Inter', Arial, Helvetica, sans-serif; font-size:12px; color:#9B9B9B; line-height:1.5;">
                    Didn't request this? You can safely ignore this email.
                  </p>
                  <p style="margin:0; font-family:'Inter', Arial, Helvetica, sans-serif; font-size:12px; color:#9B9B9B; line-height:1.5;">
                    &copy; 2026 Grand Elevation Solar
                  </p>
                </td>
              </tr>

            </table>
          </td>
        </tr>
      </table>
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


async def authenticate(
    request: Request,
    session: AsyncSession,
) -> Users | None:
    token = request.cookies.get("session_token")

    if token is None:
        return None

    statement = select(Session).where(Session.token == token)
    result = await session.exec(statement)
    db_session = result.first()

    if db_session is None:
        return None

    if db_session.expires_at < datetime.utcnow():
        await session.delete(db_session)
        await session.commit()
        return None

    statement = select(Users).where(Users.id == db_session.user_id)
    result = await session.exec(statement)
    user = result.first()

    if user is None:
        await session.delete(db_session)
        await session.commit()
        return None

    return user
