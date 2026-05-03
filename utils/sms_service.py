import json
from datetime import datetime

import requests

from config import (
    AUTO_SEND_NOTIFICATIONS,
    DEFAULT_COUNTRY_CODE,
    MSG91_AUTH_KEY,
    MSG91_FLOW_ID,
    MSG91_ROUTE,
    MSG91_SENDER_ID,
    MSG91_UNICODE,
)
from models.database import get_conn

MSG91_FLOW_URL = "https://api.msg91.com/api/v5/flow/"
TIMEOUT_SECONDS = 20

ALLOWED_SMS_ROLES = {
    "patient",
    "doctor",
    "doctor_registration",
    "doctor_approval",
    "doctor_payout",
    "hospital",
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_phone(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    default_cc = "".join(ch for ch in DEFAULT_COUNTRY_CODE if ch.isdigit()) or "91"
    if len(digits) == 10:
        return f"{default_cc}{digits}"
    if len(digits) == len(default_cc) + 10 and digits.startswith(default_cc):
        return digits
    return ""


def msg91_is_configured() -> bool:
    return bool(MSG91_AUTH_KEY and MSG91_FLOW_ID)


def send_sms(to_number: str, body: str):
    if not msg91_is_configured():
        return False, "MSG91 is not configured. Add MSG91_AUTH_KEY and MSG91_FLOW_ID in .env.", None, None

    normalized = normalize_phone(to_number)
    if not normalized:
        return False, "Recipient mobile number is invalid for SMS delivery.", None, None

    payload = {
        "flow_id": MSG91_FLOW_ID,
        "sender": MSG91_SENDER_ID,
        "route": MSG91_ROUTE,
        "unicode": MSG91_UNICODE,
        "recipients": [
            {
                "mobiles": normalized,
                "VAR1": (body or "").strip(),
            }
        ],
    }
    headers = {
        "authkey": MSG91_AUTH_KEY,
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            MSG91_FLOW_URL,
            headers=headers,
            json=payload,
            timeout=TIMEOUT_SECONDS,
        )
        try:
            data = response.json()
        except Exception:
            data = {"raw": response.text}

        if response.ok and str(data.get("type", "")).lower() == "success":
            provider_id = str(data.get("message") or "").strip()
            return True, "queued", provider_id, data

        error_text = str(data.get("message") or response.text or "MSG91 request failed").strip()
        return False, error_text, None, data
    except Exception as exc:  # pragma: no cover
        return False, str(exc), None, None


def process_pending_notifications(limit: int = 20) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, recipient_role, recipient_value, message_text, channel, provider_name
        FROM notifications
        WHERE UPPER(COALESCE(delivery_status, '')) = 'QUEUED'
        ORDER BY id ASC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cur.fetchall()
    if not rows:
        conn.close()
        return 0

    processed = 0
    now = _now()
    for row in rows:
        role = (row["recipient_role"] or "").strip().lower()
        channel = (row["channel"] or "SMS").strip().upper()
        target = (row["recipient_value"] or "").strip()
        text = (row["message_text"] or "").strip()

        if channel != "SMS" or role not in ALLOWED_SMS_ROLES:
            cur.execute(
                """
                UPDATE notifications
                SET delivery_status='SKIPPED', failure_reason='Channel not configured for auto send', updated_at=?
                WHERE id=?
                """,
                (now, row["id"]),
            )
            processed += 1
            continue

        ok, result_text, message_id, payload = send_sms(target, text)
        if ok:
            cur.execute(
                """
                UPDATE notifications
                SET provider_name='msg91', provider_message_id=?, provider_payload=?, delivery_status='SENT', sent_at=?, updated_at=?
                WHERE id=?
                """,
                (message_id or "", json.dumps(payload or {}, ensure_ascii=False), now, now, row["id"]),
            )
        else:
            cur.execute(
                """
                UPDATE notifications
                SET provider_name='msg91', delivery_status='FAILED', failure_reason=?, updated_at=?
                WHERE id=?
                """,
                (result_text[:500], now, row["id"]),
            )
        processed += 1

    conn.commit()
    conn.close()
    return processed


def maybe_process_pending_notifications(limit: int = 10) -> int:
    if not AUTO_SEND_NOTIFICATIONS:
        return 0
    return process_pending_notifications(limit=limit)
