import json
from datetime import datetime
from models.database import get_conn


def _clean(value):
    if value is None:
        return ""
    return str(value).strip()


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def queue_notifications(
    lead_id: int,
    patient_phone: str,
    doctor_phone: str,
    hospital_contact: str,
    doctor_name: str,
    patient_name: str,
    hospital_name: str,
    provider_name: str = "whatsapp",
    channel: str = "WHATSAPP"
):
    if not lead_id:
        return

    patient_phone = _clean(patient_phone)
    doctor_phone = _clean(doctor_phone)
    hospital_contact = _clean(hospital_contact)
    doctor_name = _clean(doctor_name)
    patient_name = _clean(patient_name)
    hospital_name = _clean(hospital_name)

    created_at = _now()

    messages = []

    if patient_phone:
        messages.append((
            lead_id,
            "patient",
            patient_phone,
            channel,
            provider_name,
            "",
            f"Dear {patient_name}, your referral has been submitted successfully. Hospital: {hospital_name}.",
            "QUEUED",
            None,
            None,
            None,
            None,
            None,
            None,
            created_at,
            created_at
        ))

    if doctor_phone:
        messages.append((
            lead_id,
            "doctor",
            doctor_phone,
            channel,
            provider_name,
            "",
            f"Mr. {patient_name} has been successfully referred to KIMS Saveera. You will receive referral benefits after confirmation.",
            "QUEUED",
            None,
            None,
            None,
            None,
            None,
            None,
            created_at,
            created_at
        ))

    if hospital_contact:
        messages.append((
            lead_id,
            "hospital",
            hospital_contact,
            channel,
            provider_name,
            "",
            f"Dr. {doctor_name} has referred a patient for advanced treatment. Please follow up.",
            "QUEUED",
            None,
            None,
            None,
            None,
            None,
            None,
            created_at,
            created_at
        ))

    messages.append((
        lead_id,
        "admin_team",
        "ADMIN_TEAM",
        channel,
        provider_name,
        "",
        f"Admin Team: referral {lead_id} created for patient {patient_name}. Doctor: {doctor_name}. Hospital: {hospital_name}.",
        "QUEUED",
        None,
        None,
        None,
        None,
        None,
        None,
        created_at,
        created_at
    ))

    if not messages:
        return

    conn = get_conn()
    cur = conn.cursor()

    try:
        for row in messages:
            cur.execute("""
                INSERT INTO notifications(
                    lead_id,
                    recipient_role,
                    recipient_value,
                    channel,
                    provider_name,
                    provider_message_id,
                    message_text,
                    delivery_status,
                    sent_at,
                    delivered_at,
                    read_at,
                    failed_at,
                    failure_reason,
                    provider_payload,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, row)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def mark_notification_sent(notification_id: int, provider_message_id: str = "", provider_payload=None):
    conn = get_conn()
    cur = conn.cursor()

    payload_text = json.dumps(provider_payload, ensure_ascii=False) if provider_payload is not None else None
    now = _now()

    cur.execute("""
        UPDATE notifications
        SET provider_message_id = ?,
            provider_payload = COALESCE(?, provider_payload),
            delivery_status = 'SENT',
            sent_at = ?,
            updated_at = ?
        WHERE id = ?
    """, (provider_message_id, payload_text, now, now, notification_id))

    conn.commit()
    conn.close()


def update_notification_status_by_provider_id(provider_message_id: str, new_status: str, provider_payload=None, failure_reason: str = ""):
    if not provider_message_id:
        return False

    status = (new_status or "").strip().upper()
    payload_text = json.dumps(provider_payload, ensure_ascii=False) if provider_payload is not None else None
    now = _now()

    delivered_at = None
    read_at = None
    failed_at = None

    if status in ("DELIVERED",):
        delivered_at = now
    elif status in ("READ",):
        read_at = now
    elif status in ("FAILED",):
        failed_at = now

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        UPDATE notifications
        SET delivery_status = ?,
            delivered_at = COALESCE(?, delivered_at),
            read_at = COALESCE(?, read_at),
            failed_at = COALESCE(?, failed_at),
            failure_reason = CASE WHEN ? != '' THEN ? ELSE failure_reason END,
            provider_payload = COALESCE(?, provider_payload),
            updated_at = ?
        WHERE provider_message_id = ?
    """, (
        status,
        delivered_at,
        read_at,
        failed_at,
        failure_reason,
        failure_reason,
        payload_text,
        now,
        provider_message_id
    ))

    changed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def update_notification_status_by_id(notification_id: int, new_status: str, provider_message_id: str = "", provider_payload=None, failure_reason: str = ""):
    status = (new_status or "").strip().upper()
    payload_text = json.dumps(provider_payload, ensure_ascii=False) if provider_payload is not None else None
    now = _now()

    delivered_at = None
    read_at = None
    failed_at = None
    sent_at = None

    if status == "SENT":
        sent_at = now
    elif status == "DELIVERED":
        delivered_at = now
    elif status == "READ":
        read_at = now
    elif status == "FAILED":
        failed_at = now

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        UPDATE notifications
        SET provider_message_id = CASE WHEN ? != '' THEN ? ELSE provider_message_id END,
            delivery_status = ?,
            sent_at = COALESCE(?, sent_at),
            delivered_at = COALESCE(?, delivered_at),
            read_at = COALESCE(?, read_at),
            failed_at = COALESCE(?, failed_at),
            failure_reason = CASE WHEN ? != '' THEN ? ELSE failure_reason END,
            provider_payload = COALESCE(?, provider_payload),
            updated_at = ?
        WHERE id = ?
    """, (
        provider_message_id,
        provider_message_id,
        status,
        sent_at,
        delivered_at,
        read_at,
        failed_at,
        failure_reason,
        failure_reason,
        payload_text,
        now,
        notification_id
    ))

    conn.commit()
    conn.close()

def requeue_notification(notification_id: int):
    now = _now()
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        UPDATE notifications
        SET delivery_status = 'QUEUED',
            sent_at = NULL,
            delivered_at = NULL,
            read_at = NULL,
            failed_at = NULL,
            failure_reason = '',
            provider_message_id = '',
            updated_at = ?
        WHERE id = ?
    """, (now, notification_id))

    changed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def queue_doctor_registration_message(doctor_phone: str, provider_name: str = "twilio", channel: str = "SMS"):
    doctor_phone = _clean(doctor_phone)
    if not doctor_phone:
        return
    now = _now()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO notifications(
            lead_id, recipient_role, recipient_value, channel, provider_name, provider_message_id,
            message_text, delivery_status, sent_at, delivered_at, read_at, failed_at,
            failure_reason, provider_payload, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        None, "doctor_registration", doctor_phone, channel, provider_name, "",
        "Thanks for registering. Our team will verify your registration.",
        "QUEUED", None, None, None, None, None, None, now, now
    ))
    conn.commit()
    conn.close()


def queue_doctor_approved_message(doctor_phone: str, provider_name: str = "twilio", channel: str = "SMS"):
    doctor_phone = _clean(doctor_phone)
    if not doctor_phone:
        return
    now = _now()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO notifications(
            lead_id, recipient_role, recipient_value, channel, provider_name, provider_message_id,
            message_text, delivery_status, sent_at, delivered_at, read_at, failed_at,
            failure_reason, provider_payload, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        None, "doctor_approval", doctor_phone, channel, provider_name, "",
        "Your registration has been approved successfully.",
        "QUEUED", None, None, None, None, None, None, now, now
    ))
    conn.commit()
    conn.close()


def queue_referral_paid_message(lead_id: int, doctor_phone: str, patient_name: str, provider_name: str = "twilio", channel: str = "SMS"):
    doctor_phone = _clean(doctor_phone)
    patient_name = _clean(patient_name)
    if not doctor_phone:
        return
    now = _now()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO notifications(
            lead_id, recipient_role, recipient_value, channel, provider_name, provider_message_id,
            message_text, delivery_status, sent_at, delivered_at, read_at, failed_at,
            failure_reason, provider_payload, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        lead_id, "doctor_payout", doctor_phone, channel, provider_name, "",
        f"Your referral incentive for patient {patient_name} has been processed successfully. Thank you for your support.",
        "QUEUED", None, None, None, None, None, None, now, now
    ))
    conn.commit()
    conn.close()
