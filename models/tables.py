from datetime import datetime
import os
import sqlite3
from werkzeug.security import generate_password_hash
from config import BASE_DIR
from models.database import get_conn


def init_db():
    os.makedirs(os.path.join(BASE_DIR, "database"), exist_ok=True)

    conn = get_conn()
    c = conn.cursor()

    # -----------------------------
    # USERS
    # -----------------------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        role TEXT NOT NULL CHECK(role IN ('admin','doctor','hospital')),

        display_name TEXT NOT NULL,
        hospital_name TEXT,

        phone TEXT UNIQUE,
        email TEXT UNIQUE,
        gender TEXT,
        registered_as TEXT,

        address TEXT,
        city_name TEXT,
        pincode TEXT,

        pan_number TEXT,
        aadhar_number TEXT,
        pan_file TEXT,
        aadhar_file TEXT,

        account_number TEXT,
        ifsc_code TEXT,
        upi_id TEXT,

        login_id TEXT UNIQUE,
        organization_name TEXT,

        password TEXT,
        secret_code TEXT,

        approval_status TEXT NOT NULL DEFAULT 'approved',
        qr_generated INTEGER NOT NULL DEFAULT 0,

        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # -----------------------------
    # CLINICS
    # -----------------------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS clinics(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token TEXT UNIQUE NOT NULL,
        doctor_user_id INTEGER NOT NULL,
        hospital_user_id INTEGER NOT NULL,
        clinic_name TEXT NOT NULL,
        area TEXT,
        upi_id TEXT,
        contact_number TEXT,
        qr_file TEXT,
        scan_count INTEGER NOT NULL DEFAULT 0,
        last_scanned_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(doctor_user_id) REFERENCES users(id),
        FOREIGN KEY(hospital_user_id) REFERENCES users(id)
    )
    """)
    # -----------------------------
    # LEADS
    # -----------------------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS leads(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        clinic_id INTEGER NOT NULL,
        doctor_user_id INTEGER NOT NULL,
        hospital_user_id INTEGER NOT NULL,
        patient_name TEXT NOT NULL,
        patient_phone TEXT NOT NULL,
        disease_notes TEXT,
        referral_note TEXT,
        consent_yes INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'NEW',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(clinic_id) REFERENCES clinics(id),
        FOREIGN KEY(doctor_user_id) REFERENCES users(id),
        FOREIGN KEY(hospital_user_id) REFERENCES users(id)
    )
    """)

    # -----------------------------
    # REFERRALS / PAYOUTS
    # -----------------------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS referrals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL UNIQUE,
        doctor_user_id INTEGER NOT NULL,
        hospital_user_id INTEGER NOT NULL,
        patient_name TEXT NOT NULL,
        referral_status TEXT NOT NULL DEFAULT 'pending',
        payout_status TEXT NOT NULL DEFAULT 'unpaid',
        payout_amount REAL NOT NULL DEFAULT 0,
        approved_at TEXT,
        paid_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT,
        FOREIGN KEY(lead_id) REFERENCES leads(id),
        FOREIGN KEY(doctor_user_id) REFERENCES users(id),
        FOREIGN KEY(hospital_user_id) REFERENCES users(id)
    )
    """)

    # -----------------------------
    # QR SCANS COUNT
    # -----------------------------

    c.execute("""
    CREATE TABLE IF NOT EXISTS qr_scans(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        clinic_id INTEGER NOT NULL,
        scanned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(clinic_id) REFERENCES clinics(id)
    )
    """)


    # -----------------------------
    # DOCTOR-HOSPITAL QR TRACKER
    # -----------------------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS doctor_hospital_qr(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doctor_user_id INTEGER NOT NULL,
        hospital_user_id INTEGER NOT NULL,
        qr_generated INTEGER NOT NULL DEFAULT 0,
        qr_generated_at TEXT,
        FOREIGN KEY(doctor_user_id) REFERENCES users(id),
        FOREIGN KEY(hospital_user_id) REFERENCES users(id)
    )
    """)

    # REFERRALS
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_referrals_lead_id ON referrals(lead_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_referrals_doctor_user_id ON referrals(doctor_user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_referrals_hospital_user_id ON referrals(hospital_user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referral_status ON referrals(referral_status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_referrals_payout_status ON referrals(payout_status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_referrals_created_at ON referrals(created_at)")

    # -----------------------------
    # NOTIFICATIONS
    # -----------------------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS notifications(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER,
        recipient_role TEXT NOT NULL,
        recipient_value TEXT NOT NULL,
        channel TEXT NOT NULL DEFAULT 'WHATSAPP',
        provider_name TEXT,
        provider_message_id TEXT,
        message_text TEXT NOT NULL,
        delivery_status TEXT NOT NULL DEFAULT 'QUEUED',
        sent_at TEXT,
        delivered_at TEXT,
        read_at TEXT,
        failed_at TEXT,
        failure_reason TEXT,
        provider_payload TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT,
        FOREIGN KEY(lead_id) REFERENCES leads(id)
    )
    """)

    conn.commit()

    # keep existing DB compatible
    ensure_notification_tracking_columns(conn)
    ensure_referral_tracking_columns(conn)
    ensure_column(conn, "clinics", "scan_count", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(conn, "clinics", "last_scanned_at", "TEXT")

    create_indexes(conn)
    seed_defaults(conn)

    conn.close()


def ensure_notification_tracking_columns(conn: sqlite3.Connection):
    c = conn.cursor()
    c.execute("PRAGMA table_info(notifications)")
    existing = {row[1] for row in c.fetchall()}

    required_columns = {
        "provider_name": "TEXT",
        "provider_message_id": "TEXT",
        "sent_at": "TEXT",
        "delivered_at": "TEXT",
        "read_at": "TEXT",
        "failed_at": "TEXT",
        "failure_reason": "TEXT",
        "provider_payload": "TEXT",
        "updated_at": "TEXT"
    }

    for col, definition in required_columns.items():
        if col not in existing:
            c.execute(f"ALTER TABLE notifications ADD COLUMN {col} {definition}")

    conn.commit()


def ensure_referral_tracking_columns(conn: sqlite3.Connection):
    c = conn.cursor()
    c.execute("PRAGMA table_info(referrals)")
    existing = {row[1] for row in c.fetchall()}

    required_columns = {
        "referral_status": "TEXT NOT NULL DEFAULT 'pending'",
        "payout_status": "TEXT NOT NULL DEFAULT 'unpaid'",
        "payout_amount": "REAL NOT NULL DEFAULT 0",
        "approved_at": "TEXT",
        "paid_at": "TEXT",
        "updated_at": "TEXT"
    }

    for col, definition in required_columns.items():
        if col not in existing:
            c.execute(f"ALTER TABLE referrals ADD COLUMN {col} {definition}")

    conn.commit()


def create_indexes(conn: sqlite3.Connection):
    c = conn.cursor()

    # USERS
    c.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_users_login_id ON users(login_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_users_display_name ON users(display_name)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_users_hospital_name ON users(hospital_name)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_users_approval_status ON users(approval_status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_users_registered_as ON users(registered_as)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_users_pan_number ON users(pan_number)")

    # CLINICS
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_clinics_token ON clinics(token)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_clinics_doctor_user_id ON clinics(doctor_user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_clinics_hospital_user_id ON clinics(hospital_user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_clinics_clinic_name ON clinics(clinic_name)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_clinics_contact_number ON clinics(contact_number)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_clinics_created_at ON clinics(created_at)")

    if not has_duplicate_clinics(conn):
        c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_clinic_exact
            ON clinics(doctor_user_id, hospital_user_id, clinic_name, contact_number)
        """)

    # LEADS
    c.execute("CREATE INDEX IF NOT EXISTS idx_leads_clinic_id ON leads(clinic_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_leads_doctor_user_id ON leads(doctor_user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_leads_hospital_user_id ON leads(hospital_user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_leads_patient_phone ON leads(patient_phone)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads(created_at)")

    # NOTIFICATIONS
    c.execute("CREATE INDEX IF NOT EXISTS idx_notifications_lead_id ON notifications(lead_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_notifications_recipient_role ON notifications(recipient_role)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_notifications_recipient_value ON notifications(recipient_value)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_notifications_channel ON notifications(channel)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_notifications_provider_name ON notifications(provider_name)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_notifications_provider_message_id ON notifications(provider_message_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_notifications_delivery_status ON notifications(delivery_status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_notifications_sent_at ON notifications(sent_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_notifications_delivered_at ON notifications(delivered_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_notifications_read_at ON notifications(read_at)")

    # QR SCAN HISTORY
    c.execute("CREATE INDEX IF NOT EXISTS idx_qr_scans_clinic_id ON qr_scans(clinic_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_qr_scans_scanned_at ON qr_scans(scanned_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_clinics_scan_count ON clinics(scan_count)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_clinics_last_scanned_at ON clinics(last_scanned_at)")


    # DOCTOR-HOSPITAL QR
    c.execute("CREATE INDEX IF NOT EXISTS idx_qr_doctor_user_id ON doctor_hospital_qr(doctor_user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_qr_hospital_user_id ON doctor_hospital_qr(hospital_user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_qr_generated ON doctor_hospital_qr(qr_generated)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_qr_generated_at ON doctor_hospital_qr(qr_generated_at)")


    if not has_duplicate_qr_pairs(conn):
        c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_doctor_hospital_qr
            ON doctor_hospital_qr(doctor_user_id, hospital_user_id)
        """)

    conn.commit()


def has_duplicate_qr_pairs(conn: sqlite3.Connection) -> bool:
    c = conn.cursor()
    c.execute("""
        SELECT doctor_user_id, hospital_user_id, COUNT(*) AS cnt
        FROM doctor_hospital_qr
        GROUP BY doctor_user_id, hospital_user_id
        HAVING COUNT(*) > 1
        LIMIT 1
    """)
    return c.fetchone() is not None


def has_duplicate_clinics(conn: sqlite3.Connection) -> bool:
    c = conn.cursor()
    c.execute("""
        SELECT doctor_user_id, hospital_user_id, clinic_name, IFNULL(contact_number, ''), COUNT(*) AS cnt
        FROM clinics
        GROUP BY doctor_user_id, hospital_user_id, clinic_name, IFNULL(contact_number, '')
        HAVING COUNT(*) > 1
        LIMIT 1
    """)
    return c.fetchone() is not None


def ensure_column(conn, table_name, column_name, column_def):
    c = conn.cursor()
    c.execute(f"PRAGMA table_info({table_name})")
    existing_columns = [row[1] for row in c.fetchall()]

    if column_name not in existing_columns:
        c.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
        conn.commit()


def seed_defaults(conn: sqlite3.Connection):
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    defaults = [
        {
            "role": "admin",
            "display_name": "admin",
            "hospital_name": None,
            "phone": None,
            "email": None,
            "gender": None,
            "registered_as": None,
            "address": None,
            "city_name": None,
            "pincode": None,
            "pan_number": None,
            "aadhar_number": None,
            "pan_file": None,
            "aadhar_file": None,
            "account_number": None,
            "ifsc_code": None,
            "upi_id": None,
            "login_id": "admin",
            "organization_name": None,
            "password": generate_password_hash("admin123"),
            "secret_code": generate_password_hash("ADMIN-2026"),
            "approval_status": "approved",
            "qr_generated": 0,
            "is_active": 1,
            "created_at": now
        }
    ]

    for user in defaults:
        if user["role"] == "doctor":
            c.execute("SELECT id FROM users WHERE phone=?", (user["phone"],))
        elif user["role"] == "hospital":
            c.execute("SELECT id FROM users WHERE hospital_name=?", (user["hospital_name"],))
        else:
            c.execute("SELECT id FROM users WHERE role='admin' AND display_name=?", (user["display_name"],))

        if not c.fetchone():
            c.execute("""
                INSERT INTO users(
                    role, display_name, hospital_name, phone, email, gender, registered_as,
                    address, city_name, pincode,
                    pan_number, aadhar_number, pan_file, aadhar_file,
                    account_number, ifsc_code, upi_id,
                    login_id, organization_name,
                    password, secret_code,
                    approval_status, qr_generated, is_active, created_at
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                user["role"],
                user["display_name"],
                user["hospital_name"],
                user["phone"],
                user["email"],
                user["gender"],
                user["registered_as"],
                user["address"],
                user["city_name"],
                user["pincode"],
                user["pan_number"],
                user["aadhar_number"],
                user["pan_file"],
                user["aadhar_file"],
                user["account_number"],
                user["ifsc_code"],
                user["upi_id"],
                user["login_id"],
                user["organization_name"],
                user["password"],
                user["secret_code"],
                user["approval_status"],
                user["qr_generated"],
                user["is_active"],
                user["created_at"]
            ))

    conn.commit()
