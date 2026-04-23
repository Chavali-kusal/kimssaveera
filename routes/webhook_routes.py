import json
from flask import Blueprint, request, jsonify
from utils.notifications import update_notification_status_by_provider_id

webhook_bp = Blueprint("webhook", __name__, url_prefix="/webhooks")


def _normalize_status(value: str) -> str:
    status = (value or "").strip().lower()
    mapping = {
        "queued": "SENT",
        "accepted": "SENT",
        "sending": "SENT",
        "sent": "SENT",
        "delivered": "DELIVERED",
        "read": "READ",
        "failed": "FAILED",
        "undelivered": "FAILED",
    }
    return mapping.get(status, status.upper())


@webhook_bp.route("/msg91-status", methods=["POST"])
def msg91_status():
    data = request.form.to_dict(flat=True) or request.get_json(silent=True) or {}
    provider_message_id = (data.get("message_id") or data.get("request_id") or data.get("sms_id") or "").strip()
    status = _normalize_status(data.get("status") or data.get("delivery_status") or "")
    failure_reason = (data.get("error_message") or data.get("reason") or "").strip()

    if not provider_message_id or not status:
        return jsonify({"ok": False, "error": "message_id/request_id and status are required"}), 400

    updated = update_notification_status_by_provider_id(
        provider_message_id=provider_message_id,
        new_status=status,
        provider_payload=data,
        failure_reason=failure_reason,
    )
    return jsonify({"ok": True, "updated": updated, "provider_message_id": provider_message_id, "status": status})


@webhook_bp.route("/whatsapp-status", methods=["POST"])
def whatsapp_status():
    data = request.get_json(silent=True) or {}
    provider_message_id = (data.get("provider_message_id") or data.get("message_id") or data.get("wamid") or "").strip()
    status = _normalize_status(data.get("delivery_status") or data.get("status") or "")
    failure_reason = (data.get("failure_reason") or data.get("error_message") or "").strip()

    if not provider_message_id or not status:
        return jsonify({"ok": False, "error": "provider_message_id/message_id and status are required"}), 400

    updated = update_notification_status_by_provider_id(
        provider_message_id=provider_message_id,
        new_status=status,
        provider_payload=data,
        failure_reason=failure_reason,
    )
    return jsonify({"ok": True, "updated": updated, "provider_message_id": provider_message_id, "status": status})
