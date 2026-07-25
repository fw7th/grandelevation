import base64
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
# This scope allows full sending capabilities.

# Make sure it has "www." and the full "/auth/gmail.send" path
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def get_gmail_service():
    """Handles user authentication and returns an authorized Gmail API service."""
    creds = None
    # The file token.json stores the user's access and refresh tokens.
    # It is created automatically when the authorization flow completes for the first time.
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Loads your downloaded app credentials
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def send_html_link_email():
    """Constructs and sends an HTML link email via the Gmail API."""
    try:
        service = get_gmail_service()

        # Create the email infrastructure
        message = MIMEMultipart("alternative")
        message["To"] = "okosa7th@gmail.com"  # Replace with recipient
        message["Subject"] = "Request Password Change"

        # HTML Body with a hyperlinked anchor tag
        html_content = """\
        <html>
          <body>
            <h2>Welcome!</h2>
            <p>Please click the link below to access your account:</p>
            <a href="https://example.com" style="padding: 10px 20px; background-color: #4CAF50; color: white; text-decoration: none; border-radius: 5px;">Verify Account</a>
          </body>
        </html>
        """

        message.attach(MIMEText(html_content, "html"))

        # The Gmail API requires raw messages to be base64url encoded
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        send_request = {"raw": raw_message}

        # Execute the API call
        sent_message = (
            service.users().messages().send(userId="me", body=send_request).execute()
        )
        print(f"Success! Message sent. ID: {sent_message['id']}")

    except HttpError as error:
        print(f"An error occurred: {error}")


if __name__ == "__main__":
    send_html_link_email()
