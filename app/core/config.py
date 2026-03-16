import os
from dotenv import load_dotenv

load_dotenv()


class Settings:

    # ------------------------
    # WhatsApp Configuration
    # ------------------------

    WHATSAPP_TOKEN    = os.getenv("WHATSAPP_TOKEN")
    WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
    MANAGER_PHONE     = os.getenv("MANAGER_PHONE")

    # ------------------------
    # App Config
    # ------------------------

    APP_ENV = os.getenv("APP_ENV", "development")

    def __init__(self):
        missing = []
        if not self.WHATSAPP_TOKEN:
            missing.append("WHATSAPP_TOKEN")
        if not self.WHATSAPP_PHONE_ID:
            missing.append("WHATSAPP_PHONE_ID")
        if not self.MANAGER_PHONE:
            missing.append("MANAGER_PHONE")
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}"
            )


settings = Settings()