import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV == "production"

SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    if IS_PRODUCTION:
        raise RuntimeError("SECRET_KEY environment variable is required in production.")
    SECRET_KEY = "dev-only-secret-change-me"

DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "database", "healthqr.db"))
if not os.path.isabs(DATABASE_PATH):
    DATABASE_PATH = os.path.join(BASE_DIR, DATABASE_PATH)

QR_FOLDER = os.getenv("QR_FOLDER", os.path.join(BASE_DIR, "qr_codes"))
if not os.path.isabs(QR_FOLDER):
    QR_FOLDER = os.path.join(BASE_DIR, QR_FOLDER)

DOCTOR_DOCS_FOLDER = os.getenv("DOCTOR_DOCS_FOLDER", os.path.join(BASE_DIR, "private_uploads", "doctor_docs"))
if not os.path.isabs(DOCTOR_DOCS_FOLDER):
    DOCTOR_DOCS_FOLDER = os.path.join(BASE_DIR, DOCTOR_DOCS_FOLDER)

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:5000").rstrip("/")
DEFAULT_HOSPITAL_NAME = "KIMS SAVEERA"
APP_NAME = "HealthQR Referral"

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "").strip()
TWILIO_STATUS_CALLBACK_URL = os.getenv("TWILIO_STATUS_CALLBACK_URL", "").strip()
DEFAULT_COUNTRY_CODE = os.getenv("DEFAULT_COUNTRY_CODE", "+91").strip() or "+91"
AUTO_SEND_NOTIFICATIONS = _get_bool("AUTO_SEND_NOTIFICATIONS", default=False)
