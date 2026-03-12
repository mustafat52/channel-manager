import os
import pickle
import base64
from email import message_from_bytes

from google.auth.transport.requests import Request
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def get_gmail_service():

    creds = None

    if not os.path.exists("token.pickle"):
        raise Exception("token.pickle not found")

    with open("token.pickle", "rb") as token:
        creds = pickle.load(token)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    service = build("gmail", "v1", credentials=creds)

    return service


def fetch_booking_emails():

    service = get_gmail_service()

    messages = []

    response = service.users().messages().list(
        userId="me",
        q="is:read",
        maxResults=50
    ).execute()

    messages.extend(response.get("messages", []))

    while "nextPageToken" in response:
        response = service.users().messages().list(
            userId="me",
            q="is:read",
            pageToken=response["nextPageToken"]
        ).execute()

        messages.extend(response.get("messages", []))

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

        subject = email_message.get("subject")
        sender = email_message.get("from")
        date = email_message.get("date")

        body = ""

        if email_message.is_multipart():

            for part in email_message.walk():

                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode(errors="ignore")
                    break

        else:

            body = email_message.get_payload(decode=True).decode(errors="ignore")

        # fallback if plain text not found
        if not body:

            for part in email_message.walk():

                if part.get_content_type() == "text/html":
                    body = part.get_payload(decode=True).decode(errors="ignore")
                    break

        emails.append({
            "message_id": msg["id"],
            "subject": subject,
            "from": sender,
            "date": date,
            "body": body
        })

    return emails


def mark_email_read(message_id):

    service = get_gmail_service()

    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"removeLabelIds": ["UNREAD"]}
    ).execute()