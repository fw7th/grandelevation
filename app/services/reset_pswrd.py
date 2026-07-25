"""DECIDE AND PICK"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from fastapi.responses import ORJSONResponse


def send_otp_smtp(user_email, otp_code):
    # Configuration
    sender_email = "your-gmail@gmail.com"
    # Use the 16-character App Password, NOT your regular login password
    app_password = "xxxx xxxx xxxx xxxx"

    # Message Setup
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = user_email
    msg["Subject"] = "Your Password Reset OTP"

    body = f"Your one-time password for resetting your account is: {otp_code}\nThis code expires in 10 minutes."
    msg.attach(MIMEText(body, "plain"))

    try:
        # Connect to Gmail SMTP server
        server = smtplib.SMTP("://gmail.com", 587)
        server.starttls()  # Secure the connection
        server.login(sender_email, app_password)

        # Send Email
        server.sendmail(sender_email, user_email, msg.as_string())
        server.quit()
        print("OTP email sent successfully!")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


# Example Usage
# send_otp_smtp("user@example.com", "482019")

"""OR"""


import base64
from email.mime.text import MIMEText

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Only requires the send scope (No expensive security audit needed)
SCOPES = ["https://googleapis.com"]


def get_gmail_service():
    # Looks for existing user tokens, otherwise authenticates
    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    creds = flow.run_local_server(port=0)
    return build("gmail", "v1", credentials=creds)


def send_otp_api(user_email, otp_code):
    try:
        service = get_gmail_service()

        # Create message
        message = MIMEText(f"Your password reset OTP is: {otp_code}")
        message["to"] = user_email
        message["subject"] = "Your Password Reset OTP"

        # Encode to base64 string as required by Gmail API
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        send_request = {"raw": raw_message}

        # Execute the send command
        str_message = (
            service.users().messages().send(userId="me", body=send_request).execute()
        )
        print(f"Message Sent ID: {str_message['id']}")
        return True

    except HttpError as error:
        print(f"An error occurred: {error}")
        return False


# Example Usage
# send_otp_api("user@example.com", "482019")
