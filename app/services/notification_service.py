import requests

from app.core.config import settings

def send_whatsapp_message(message: str):

    url = f"https://graph.facebook.com/v18.0/{settings.WHATSAPP_PHONE_ID}/messages"

    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": settings.MANAGER_PHONE,
        "type": "text",
        "text": {"body": message}
    }

    print("Sending WhatsApp message...")
    print(payload)

    response = requests.post(url, headers=headers, json=payload)

    print("WhatsApp response:", response.json())

    return response.json()