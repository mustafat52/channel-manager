from app.services.notification_service import send_whatsapp_message


if __name__ == "__main__":

    message = """
Test Notification

Your WhatsApp integration is working.
"""

    response = send_whatsapp_message(message)

    print(response)