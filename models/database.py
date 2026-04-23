import sqlite3
from config import DATABASE_PATH


def get_conn():
    conn = sqlite3.connect(
        DATABASE_PATH,
        timeout=10,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA cache_size = -20000")

    return conn


def optimize_database():
    """
    Safe DB optimization for existing project.
    Call once during app startup.
    """

    conn = get_conn()
    cur = conn.cursor()

    try:
        # -----------------------------
        # USERS
        # -----------------------------
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_login_id ON users(login_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_approval_status ON users(approval_status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_registered_as ON users(registered_as)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_display_name ON users(display_name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_hospital_name ON users(hospital_name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_pan_number ON users(pan_number)")

        # -----------------------------
        # CLINICS
        # -----------------------------
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_clinics_token ON clinics(token)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_clinics_doctor_user_id ON clinics(doctor_user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_clinics_hospital_user_id ON clinics(hospital_user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_clinics_clinic_name ON clinics(clinic_name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_clinics_created_at ON clinics(created_at)")

        # Optional duplicate control for exact same clinic record
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_clinic_exact
            ON clinics(
                doctor_user_id,
                hospital_user_id,
                clinic_name,
                contact_number
            )
        """)

        # -----------------------------
        # LEADS
        # -----------------------------
        cur.execute("CREATE INDEX IF NOT EXISTS idx_leads_clinic_id ON leads(clinic_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_leads_doctor_user_id ON leads(doctor_user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_leads_hospital_user_id ON leads(hospital_user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_leads_patient_phone ON leads(patient_phone)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads(created_at)")

        # -----------------------------
        # NOTIFICATIONS
        # -----------------------------
        cur.execute("CREATE INDEX IF NOT EXISTS idx_notifications_lead_id ON notifications(lead_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_notifications_recipient_role ON notifications(recipient_role)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_notifications_recipient_value ON notifications(recipient_value)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at)")

        # -----------------------------
        # DOCTOR HOSPITAL QR
        # -----------------------------
        cur.execute("CREATE INDEX IF NOT EXISTS idx_qr_doctor_user_id ON doctor_hospital_qr(doctor_user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_qr_hospital_user_id ON doctor_hospital_qr(hospital_user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_qr_generated ON doctor_hospital_qr(qr_generated)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_qr_generated_at ON doctor_hospital_qr(qr_generated_at)")

        # Strong duplicate protection
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_doctor_hospital_qr
            ON doctor_hospital_qr(doctor_user_id, hospital_user_id)
        """)

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()