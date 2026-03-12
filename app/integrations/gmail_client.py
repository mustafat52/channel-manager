import os
import pickle

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_gmail_service():

    creds = None

    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json",
                SCOPES
            )

            creds = flow.run_local_server(port=0)

        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    service = build("gmail", "v1", credentials=creds)

    return service


import base64
from email import message_from_bytes


def fetch_booking_emails():

    service = get_gmail_service()

    results = service.users().messages().list(
        userId="me",
        q="is:read newer_than:7d",      #later change it to unread and 2d
        maxResults=50
    ).execute()

    messages = results.get("messages", [])

    emails = []

    for msg in messages:

        
        message = service.users().messages().get(
            userId="me",
            id=msg["id"],
            format="raw"
        ).execute()

        service.users().messages().modify(
            userId="me",
            id=msg["id"],
            body={"removeLabelIds": ["UNREAD"]}
        ).execute()

        raw = base64.urlsafe_b64decode(message["raw"])

        email_message = message_from_bytes(raw)

        body = ""

        if email_message.is_multipart():

            for part in email_message.walk():

                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode()

        else:

            body = email_message.get_payload(decode=True).decode()

        emails.append({
            "message_id": msg["id"],
            "body": body
        })

    return emails    