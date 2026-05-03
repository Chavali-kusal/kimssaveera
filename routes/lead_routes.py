import re
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response
from config import DEFAULT_HOSPITAL_NAME
from models.database import get_conn
from utils.notifications import queue_notifications
from utils.sms_service import maybe_process_pending_notifications

lead_bp = Blueprint("lead", __name__)


@lead_bp.route("/l/<token>", methods=["GET"])
def lead_form(token):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT c.id AS clinic_id,
               c.token,
               c.clinic_name,
               c.area,
               d.id AS doctor_user_id,
               d.display_name AS doctor_name,
               d.phone AS doctor_phone,
               h.id AS hospital_user_id,
               h.hospital_name
        FROM clinics c
        JOIN users d ON d.id = c.doctor_user_id
        JOIN users h ON h.id = c.hospital_user_id
        WHERE c.token = ?
        """,
        (token,),
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return "Invalid QR or referral link.", 404

    return render_template("lead/form.html", row=row)


@lead_bp.route("/submit_lead", methods=["POST"])
def submit_lead():
    clinic_id = request.form.get("clinic_id", "").strip()
    doctor_user_id = request.form.get("doctor_user_id", "").strip()
    hospital_user_id = request.form.get("hospital_user_id", "").strip()
    patient_name = request.form.get("patient_name", "").strip()
    patient_phone = request.form.get("patient_phone", "").strip()
    disease_notes = request.form.get("disease_notes", "").strip()
    referral_note = request.form.get("referral_note", "").strip()
    token = request.form.get("token", "").strip()
    consent_yes = 1 if request.form.get("consent_yes") else 0
    submit_latitude = request.form.get("submit_latitude", "").strip()
    submit_longitude = request.form.get("submit_longitude", "").strip()
    submit_accuracy = request.form.get("submit_accuracy", "").strip()
    submit_location_status = request.form.get("submit_location_status", "not_requested").strip()
    location_captured_at = request.form.get("location_captured_at", "").strip()

    if submit_latitude and submit_longitude and submit_location_status in ("", "not_requested"):
        submit_location_status = "captured"
    if not location_captured_at and submit_location_status and submit_location_status != "not_requested":
        location_captured_at = datetime.now().isoformat(timespec="seconds")

    if not all([clinic_id, doctor_user_id, hospital_user_id, patient_name, patient_phone]) or consent_yes != 1:
        flash("All required fields must be filled and consent must be accepted.", "error")
        if token:
            return redirect(url_for("lead.lead_form", token=token))
        return redirect(request.referrer or "/")

    if not re.fullmatch(r"\d{10}", patient_phone):
        flash("Patient phone must be exactly 10 digits.", "error")
        if token:
            return redirect(url_for("lead.lead_form", token=token))
        return redirect(request.referrer or "/")

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT c.id,
               d.display_name AS doctor_name,
               d.phone AS doctor_phone,
               h.hospital_name,
               h.phone AS hospital_phone,
               h.email AS hospital_email,
               h.login_id AS hospital_login_id
        FROM clinics c
        JOIN users d ON d.id = c.doctor_user_id
        JOIN users h ON h.id = c.hospital_user_id
        WHERE c.id = ? AND d.id = ? AND h.id = ?
        """,
        (clinic_id, doctor_user_id, hospital_user_id),
    )
    clinic = cur.fetchone()

    if not clinic:
        conn.close()
        return "Referral source not found.", 404

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute(
        """
        INSERT INTO leads(
            clinic_id,
            doctor_user_id,
            hospital_user_id,
            patient_name,
            patient_phone,
            disease_notes,
            referral_note,
            consent_yes,
            submit_latitude,
            submit_longitude,
            submit_accuracy,
            submit_location_status,
            location_captured_at,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            clinic_id,
            doctor_user_id,
            hospital_user_id,
            patient_name,
            patient_phone,
            disease_notes,
            referral_note,
            consent_yes,
            submit_latitude,
            submit_longitude,
            submit_accuracy,
            submit_location_status,
            location_captured_at,
            created_at,
        ),
    )
    conn.commit()
    lead_id = cur.lastrowid

    cur.execute(
        """
        INSERT INTO referrals(
            lead_id, doctor_user_id, hospital_user_id, patient_name, referral_status, payout_status, payout_amount, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, 'pending', 'unpaid', 0, ?, ?)
        """,
        (lead_id, doctor_user_id, hospital_user_id, patient_name, created_at, created_at),
    )
    conn.commit()
    conn.close()

    hospital_contact = (clinic["hospital_phone"] or "").strip()

    queue_notifications(
        lead_id=lead_id,
        patient_phone=patient_phone,
        doctor_phone=clinic["doctor_phone"],
        hospital_contact=hospital_contact,
        doctor_name=clinic["doctor_name"],
        patient_name=patient_name,
        hospital_name=clinic["hospital_name"] or DEFAULT_HOSPITAL_NAME,
        provider_name="msg91",
        channel="SMS",
    )
    maybe_process_pending_notifications(limit=10)

    return redirect(url_for("lead.submitted", lead_id=lead_id))


@lead_bp.route("/submitted/<int:lead_id>")
def submitted(lead_id: int):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT l.id,
               l.patient_name,
               h.hospital_name
        FROM leads l
        JOIN users h ON h.id = l.hospital_user_id
        WHERE l.id = ?
        """,
        (lead_id,),
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return render_template("lead/submitted.html", ok=False, lead=None), 404

    return render_template("lead/submitted.html", ok=True, lead=row)