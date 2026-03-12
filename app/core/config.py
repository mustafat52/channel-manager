import os
from dotenv import load_dotenv

load_dotenv()


class Settings:

    # ------------------------
    # WhatsApp Configuration
    # ------------------------

    WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")

    WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")

    MANAGER_PHONE = os.getenv("MANAGER_PHONE")

    # ------------------------
    # App Config
    # ------------------------

    APP_ENV = os.getenv("APP_ENV", "development")


settings = Settings()