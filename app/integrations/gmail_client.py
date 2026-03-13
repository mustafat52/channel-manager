import os
<<<<<<< HEAD
import pickle
import base64
from email import message_from_bytes

=======
import base64
import logging

from email import message_from_bytes
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError
from google_auth_oauthlib.flow import InstalledAppFlow
>>>>>>> dev
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Suppress the noisy "file_cache is only supported with oauth2client<4.0.0" warning
logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)

<<<<<<< HEAD
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
=======
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SCOPES
# gmail.readonly  — read email body content
# gmail.modify    — mark emails as read after processing
# ---------------------------------------------------------------------------
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

# ---------------------------------------------------------------------------
# ALLOWED SENDERS
# Only process emails from known booking platform domains.
# Bypassed when TEST_MODE=true in .env (for testing with forwarded emails).
# ALWAYS set TEST_MODE=false before handing over to client.
# ---------------------------------------------------------------------------
ALLOWED_SENDER_DOMAINS = {
    "airbnb.com",
    "vrbo.com",
    "homeaway.com",
    "booking.com",
}

# ---------------------------------------------------------------------------
# TEST_MODE — read once at startup from .env
# true  → domain allowlist bypassed, wider query window (7d, no from: filter)
# false → production mode, tight query, strict domain enforcement
# ---------------------------------------------------------------------------
TEST_MODE = os.environ.get("TEST_MODE", "false").lower() == "true"

if TEST_MODE:
    GMAIL_QUERY = "is:unread newer_than:9d"
else:
    GMAIL_QUERY = (
        "is:unread newer_than:2d "
        "from:(airbnb.com OR vrbo.com OR homeaway.com OR booking.com)"
    )

MAX_PAGES = 10

TOKEN_PATH       = os.environ.get("GMAIL_TOKEN_PATH", "gmail_token.json")
CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json")
>>>>>>> dev


def get_gmail_service():
    """
    Build and return an authenticated Gmail API service.
    Uses safe JSON token storage instead of pickle.
    """
    creds = None

<<<<<<< HEAD
    if not os.path.exists("token.pickle"):
        raise Exception("token.pickle not found")

    with open("token.pickle", "rb") as token:
        creds = pickle.load(token)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
=======
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except Exception as e:
            logger.warning("Failed to load token file, will re-authenticate: %s", e)
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logger.info("Gmail OAuth token refreshed successfully.")
            except RefreshError as e:
                raise RuntimeError(
                    "Gmail OAuth token refresh failed — manual re-authentication required. "
                    f"Reason: {e}"
                ) from e
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"Google credentials file not found at: {CREDENTIALS_PATH}. "
                    "Set the GOOGLE_CREDENTIALS_PATH environment variable."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
            logger.info("Gmail OAuth completed, token saved to %s", TOKEN_PATH)

        with open(TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())
        os.chmod(TOKEN_PATH, 0o600)
>>>>>>> dev

    return build("gmail", "v1", credentials=creds)


<<<<<<< HEAD
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

=======
def _get_sender_domain(email_message) -> str:
    """Extract the domain from the From header of a parsed email."""
    from_header = email_message.get("From", "")
    if "<" in from_header:
        address = from_header.split("<")[-1].rstrip(">").strip()
    else:
        address = from_header.strip()
    return address.split("@")[-1].lower() if "@" in address else ""


def _extract_body(email_message) -> str:
    """
    Extract plain-text body from a parsed email message.
    Uses charset declared in the email part, falls back to utf-8.
    """
    body = ""

    if email_message.is_multipart():
        for part in email_message.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
                    break
    else:
        payload = email_message.get_payload(decode=True)
        if payload:
            charset = email_message.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="replace")

    return body


def fetch_booking_emails() -> list[dict]:
    """
    Fetch unread booking emails from Gmail.

    Returns a list of dicts:
        {
            "message_id":    str,  # Gmail message ID (deduplication key)
            "body":          str,  # Plain-text email body
            "sender_domain": str,  # e.g. "airbnb.com" (for router detection)
            "_service":      obj,  # Gmail service (for mark_email_as_read)
        }

    Emails are NOT marked as read here — the worker calls
    mark_email_as_read() only after successful processing.
    """
    if TEST_MODE:
        logger.warning(
            "TEST_MODE is ON — sender allowlist and from: filter are disabled. "
            "Set TEST_MODE=false in .env before going to production."
        )

    service = get_gmail_service()
>>>>>>> dev
    emails = []
    page_token = None
    pages_fetched = 0

    while pages_fetched < MAX_PAGES:

        list_kwargs = {
            "userId": "me",
            "q": GMAIL_QUERY,
            "maxResults": 50,
        }
        if page_token:
            list_kwargs["pageToken"] = page_token

        results = service.users().messages().list(**list_kwargs).execute()
        messages = results.get("messages", [])
        pages_fetched += 1

        for msg in messages:
            message_id = msg["id"]

            try:
                message = service.users().messages().get(
                    userId="me",
                    id=message_id,
                    format="raw",
                ).execute()

                raw = base64.urlsafe_b64decode(message["raw"])
                email_message = message_from_bytes(raw)
                sender_domain = _get_sender_domain(email_message)

                if sender_domain not in ALLOWED_SENDER_DOMAINS:
                    if TEST_MODE:
                        logger.warning(
                            "TEST_MODE: processing email %s from non-production "
                            "domain '%s'.", message_id, sender_domain,
                        )
                    else:
                        logger.warning(
                            "Skipping email %s — sender domain '%s' not in allowlist.",
                            message_id, sender_domain,
                        )
                        _mark_as_read(service, message_id)
                        continue

                body = _extract_body(email_message)

                if not body:
                    logger.warning("Email %s has no plain-text body, skipping.", message_id)
                    _mark_as_read(service, message_id)
                    continue

                emails.append({
                    "message_id":    message_id,
                    "body":          body,
                    "sender_domain": sender_domain,
                    "_service":      service,
                })

            except Exception as e:
                logger.error("Failed to fetch email %s: %s", message_id, e)
                continue

        page_token = results.get("nextPageToken")
        if not page_token:
            break

    logger.info("Fetched %d unread booking email(s).", len(emails))
    return emails


def mark_email_as_read(service, message_id: str) -> None:
    """
    Mark a single Gmail message as read (removes UNREAD label).
    Called by the worker only after successful processing.
    """
    try:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()
    except Exception as e:
        logger.warning("Failed to mark email %s as read: %s", message_id, e)


<<<<<<< HEAD
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
=======
def _mark_as_read(service, message_id: str) -> None:
    """Internal convenience wrapper."""
    mark_email_as_read(service, message_id)
>>>>>>> dev
