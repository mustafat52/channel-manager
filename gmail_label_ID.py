from dotenv import load_dotenv
load_dotenv()
from app.integrations.gmail_client import get_gmail_service

service = get_gmail_service()
labels = service.users().labels().list(userId="me").execute()
for label in labels["labels"]:
    if "process" in label["name"].lower():
        print(label["name"], "→", label["id"])