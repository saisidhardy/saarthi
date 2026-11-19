import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    SARVAM_API_KEY: str = os.getenv("SARVAM_API_KEY", "")
    SIMULATE: bool = os.getenv("SIMULATE", "true").lower() in ("true", "1", "yes")
    DEMO_OVERRIDE_HOURS: bool = os.getenv("DEMO_OVERRIDE_HOURS", "true").lower() in ("true", "1", "yes")
    DATA_DIR: str = os.getenv("DATA_DIR", "")
    DATABASE_PATH: str = os.path.join(os.getenv("DATA_DIR") or os.path.dirname(os.path.dirname(__file__)), "saarthi.db")
    SAMPLE_BOOK_PATH: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "sample_book.csv")
    
    # Cost parameters
    CALL_COST_PER_MIN: float = 3.50  # Sarvam Voice / minute
    ESTIMATED_LLM_COST_PER_CALL: float = 0.40  # Sarvam-105B tokens
    INDUSTRY_CALL_CENTRE_COST: float = 52.00
    INDUSTRY_FIELD_VISIT_COST: float = 250.00

    # Telephony Bridge Parameters (Exotel & Twilio)
    TELEPHONY_PROVIDER: str = os.getenv("TELEPHONY_PROVIDER", "simulated")
    EXOTEL_ACCOUNT_SID: str = os.getenv("EXOTEL_ACCOUNT_SID", "mock_exotel_sid")
    EXOTEL_API_KEY: str = os.getenv("EXOTEL_API_KEY", "mock_exotel_key")
    EXOTEL_API_TOKEN: str = os.getenv("EXOTEL_API_TOKEN", "mock_exotel_token")
    EXOTEL_CALLER_ID: str = os.getenv("EXOTEL_CALLER_ID", "+918047190000")
    EXOTEL_SUB_DOMAIN: str = os.getenv("EXOTEL_SUB_DOMAIN", "api.exotel.com")

    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "mock_twilio_sid")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "mock_twilio_token")
    TWILIO_FROM_NUMBER: str = os.getenv("TWILIO_FROM_NUMBER", "+18005550199")
    PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "https://saarthi.embarko.app")

settings = Settings()
