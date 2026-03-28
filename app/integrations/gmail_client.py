import os
import base64
import logging

from email import message_from_bytes
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

# ---------------------------------------------------------------------------
# ALLOWED SENDER BASE DOMAINS
# FIX: Changed from exact domain match to base-domain match.
# Real production emails come from subdomains:
#   messages.homeaway.com, payment.homeaway.com, reviews.homeaway.com
#   guest.booking.com, properties.booking.com
#   automated@airbnb.com (direct, no subdomain)
# We now check if the sender domain ENDS WITH any of these base domains.
# ---------------------------------------------------------------------------
ALLOWED_SENDER_BASE_DOMAINS = {
    "airbnb.com",
    "vrbo.com",
    "homeaway.com",
    "booking.com",
}

TEST_MODE = os.environ.get("TEST_MODE", "false").lower() == "true"

# ---------------------------------------------------------------------------
# GMAIL_LABEL_ID — the internal Gmail label ID for "to-process"
# Get this by running: python scripts/get_label_id.py
# Then set GMAIL_LABEL_ID in your .env / Railway environment variables.
# ---------------------------------------------------------------------------
GMAIL_LABEL_ID = os.environ.get("GMAIL_LABEL_ID", "")

if TEST_MODE:
    GMAIL_QUERY = "is:unread newer_than:9d"
elif GMAIL_LABEL_ID:
    # Production with label — completely decoupled from read/unread status.
    # Client can open emails freely without affecting the poller.
    GMAIL_QUERY = f"label:to-process"
else:
    # Fallback if label not set up yet
    GMAIL_QUERY = (
        "is:unread newer_than:2d "
        "from:(airbnb.com OR homeaway.com OR vrbo.com OR booking.com)"
    )

MAX_PAGES = 10

TOKEN_PATH       = os.environ.get("GMAIL_TOKEN_PATH", "gmail_token.json")
CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json")

GMAIL_TOKEN_JSON_ENV        = os.environ.get("GMAIL_TOKEN_JSON")
GOOGLE_CREDENTIALS_JSON_ENV = os.environ.get("GOOGLE_CREDENTIALS_JSON")


def _is_allowed_sender(domain: str) -> bool:
    """
    Return True if domain matches or is a subdomain of any allowed base domain.
    e.g. "messages.homeaway.com" → ends with "homeaway.com" → allowed ✅
         "guest.booking.com"     → ends with "booking.com"  → allowed ✅
         "airbnb.com"            → exact match              → allowed ✅
         "gmail.com"             → no match                 → blocked ❌
    """
    for base in ALLOWED_SENDER_BASE_DOMAINS:
        if domain == base or domain.endswith("." + base):
            return True
    return False


def _load_credentials_from_env() -> Credentials | None:
    if not GMAIL_TOKEN_JSON_ENV:
        return None
    try:
        import json
        token_data = json.loads(GMAIL_TOKEN_JSON_ENV)
        creds = Credentials.from_authorized_user_info(token_data, SCOPES)
        logger.info("Gmail token loaded from GMAIL_TOKEN_JSON environment variable.")
        return creds
    except Exception as e:
        logger.warning("Failed to load token from GMAIL_TOKEN_JSON env var: %s", e)
        return None


def _write_token(creds: Credentials) -> None:
    try:
        with open(TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())
        os.chmod(TOKEN_PATH, 0o600)
        logger.info("Gmail token saved to %s", TOKEN_PATH)
    except OSError:
        logger.info("Could not write token to disk (read-only filesystem) — token kept in memory.")


def get_gmail_service():
    creds = _load_credentials_from_env()

    if creds is None and os.path.exists(TOKEN_PATH):
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
                _write_token(creds)
            except RefreshError as e:
                raise RuntimeError(
                    "Gmail OAuth token refresh failed — manual re-authentication required. "
                    f"Reason: {e}"
                ) from e
        else:
            if GOOGLE_CREDENTIALS_JSON_ENV:
                raise RuntimeError(
                    "Gmail token is missing or invalid. Re-run OAuth locally, "
                    "then update GMAIL_TOKEN_JSON in Railway Variables with the new token."
                )
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"Google credentials file not found at: {CREDENTIALS_PATH}. "
                    "Set GOOGLE_CREDENTIALS_JSON environment variable on Railway."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
            logger.info("Gmail OAuth completed.")
            _write_token(creds)

    return build("gmail", "v1", credentials=creds)


def _get_sender_domain(email_message) -> str:
    from_header = email_message.get("From", "")
    if "<" in from_header:
        address = from_header.split("<")[-1].rstrip(">").strip()
    else:
        address = from_header.strip()
    return address.split("@")[-1].lower() if "@" in address else ""


def _extract_body(email_message) -> str:
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
    if TEST_MODE:
        logger.warning(
            "TEST_MODE is ON — sender allowlist and from: filter are disabled. "
            "Set TEST_MODE=false in .env before going to production."
        )

    service = get_gmail_service()
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

                if not _is_allowed_sender(sender_domain):
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
    Remove the 'to-process' label after successful processing (label mode),
    OR mark as read (fallback unread mode).
    Called by the worker only after successful processing.
    """
    try:
        if GMAIL_LABEL_ID:
            # Label mode — remove the to-process label.
            # Client can read emails freely without affecting the poller.
            service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": [GMAIL_LABEL_ID]},
            ).execute()
        else:
            # Fallback — mark as read
            service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()
    except Exception as e:
        logger.warning("Failed to update email %s after processing: %s", message_id, e)


def _mark_as_read(service, message_id: str) -> None:
    mark_email_as_read(service, message_id)