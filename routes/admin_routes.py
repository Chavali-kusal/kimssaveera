from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, abort, session
from werkzeug.security import generate_password_hash
from models.database import get_conn
from config import DOCTOR_DOCS_FOLDER
from utils.helpers import login_required
from utils.notifications import queue_doctor_approved_message, queue_referral_paid_message
from utils.sms_service import maybe_process_pending_notifications, process_pending_notifications
from config import BASE_DIR
import os
import re

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/doctor-approvals")
@login_required(role="admin")
def doctor_approvals():
    conn = get_conn()
    cur = conn.cursor()

    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip()
    registered_as = request.args.get("registered_as", "").strip()

    query = """
        SELECT *
        FROM users
        WHERE role='doctor'
    """
    params = []

    if search:
        query += " AND (display_name LIKE ? OR phone LIKE ? OR city_name LIKE ? OR email LIKE ?)"
        like_search = f"%{search}%"
        params.extend([like_search, like_search, like_search, like_search])

    if status:
        query += " AND approval_status=?"
        params.append(status)

    if registered_as:
        query += " AND registered_as=?"
        params.append(registered_as)

    query += " ORDER BY id DESC"

    cur.execute(query, params)
    doctors = cur.fetchall()
    conn.close()

    return render_template("admin/doctor_approvals.html", doctors=doctors)


@admin_bp.route("/doctor-approvals/<int:doctor_id>/approve", methods=["POST"])
@login_required(role="admin")
def approve_doctor(doctor_id):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        "SELECT id, phone FROM users WHERE id=? AND role='doctor'",
        (doctor_id,)
    )
    doctor = cur.fetchone()

    if not doctor:
        conn.close()
        flash("Doctor not found.", "error")
        return redirect(url_for("admin.doctor_approvals"))

    cur.execute(
        "UPDATE users SET approval_status='approved', is_active=1 WHERE id=? AND role='doctor'",
        (doctor_id,)
    )
    conn.commit()
    conn.close()

    queue_doctor_approved_message(doctor["phone"] if doctor else "")
    maybe_process_pending_notifications(limit=5)
    flash("Doctor approved successfully.", "success")
    return redirect(url_for("admin.doctor_approvals"))


@admin_bp.route("/doctor-approvals/<int:doctor_id>/reject", methods=["POST"])
@login_required(role="admin")
def reject_doctor(doctor_id):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        "SELECT id, phone FROM users WHERE id=? AND role='doctor'",
        (doctor_id,)
    )
    doctor = cur.fetchone()

    if not doctor:
        conn.close()
        flash("Doctor not found.", "error")
        return redirect(url_for("admin.doctor_approvals"))

    cur.execute(
        "UPDATE users SET approval_status='rejected', is_active=0 WHERE id=? AND role='doctor'",
        (doctor_id,)
    )
    conn.commit()
    conn.close()

    flash("Doctor rejected successfully.", "warning")
    return redirect(url_for("admin.doctor_approvals"))


@admin_bp.route("/doctor-file/<int:doctor_id>/<file_type>")
@login_required(role="admin")
def view_doctor_file(doctor_id, file_type):
    if file_type not in ("pan", "aadhar"):
        abort(404)

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT pan_file, aadhar_file
        FROM users
        WHERE id=? AND role='doctor'
    """, (doctor_id,))
    doctor = cur.fetchone()
    conn.close()

    if not doctor:
        abort(404)

    filename = doctor["pan_file"] if file_type == "pan" else doctor["aadhar_file"]

    if not filename:
        abort(404)

    filename = os.path.basename(filename)

    file_path = os.path.join(DOCTOR_DOCS_FOLDER, filename)
    if os.path.isfile(file_path):
        return send_from_directory(DOCTOR_DOCS_FOLDER, filename)

    abort(404)


@admin_bp.route("/sql-console")
@login_required(role="admin")
def sql_console():
    return render_template("admin/sql_console.html")


@admin_bp.route("/hospitals/create", methods=["GET", "POST"])
@login_required(role="admin")
def create_hospital():
    if request.method == "POST":
        hospital_name = request.form.get("hospital_name", "").strip()
        login_id = request.form.get("login_id", "").strip()
        email = request.form.get("email", "").strip()
        city_name = request.form.get("city_name", "").strip()
        password = request.form.get("password", "").strip()
        secret_code = request.form.get("secret_code", "").strip()

        if not hospital_name or not password or not secret_code:
            flash("Hospital name, password, and secret key are required.", "error")
            return render_template("admin/create_hospital.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("admin/create_hospital.html")

        if len(secret_code) < 4:
            flash("Secret key must be at least 4 characters.", "error")
            return render_template("admin/create_hospital.html")

        if not login_id:
            login_id = hospital_name

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id FROM users
            WHERE role='hospital' AND (hospital_name=? OR login_id=? OR (? <> '' AND email=?))
            LIMIT 1
            """,
            (hospital_name, login_id, email, email),
        )
        existing = cur.fetchone()
        if existing:
            conn.close()
            flash("Hospital already exists with same hospital name, login ID, or email.", "error")
            return render_template("admin/create_hospital.html")

        cur.execute(
            """
            INSERT INTO users(
                role, display_name, hospital_name, phone, email, gender, registered_as,
                address, city_name, pincode,
                pan_number, aadhar_number, pan_file, aadhar_file,
                account_number, ifsc_code, upi_id,
                login_id, organization_name,
                password, secret_code,
                approval_status, qr_generated, is_active
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                'hospital', hospital_name, hospital_name, None, email or None, None, None,
                None, city_name or None, None,
                None, None, None, None,
                None, None, None,
                login_id, hospital_name,
                generate_password_hash(password), generate_password_hash(secret_code),
                'approved', 0, 1,
            ),
        )
        conn.commit()
        conn.close()
        flash("Hospital created successfully.", "success")
        return redirect(url_for("admin.create_hospital"))

    return render_template("admin/create_hospital.html")


@admin_bp.route("/referrals/<int:referral_id>/confirm", methods=["POST"])
@login_required(role="hospital")
def confirm_referral(referral_id):
    hospital_user_id = session.get("user_id")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE referrals
        SET referral_status='confirmed',
            approved_at=CURRENT_TIMESTAMP,
            updated_at=CURRENT_TIMESTAMP
        WHERE id=? AND hospital_user_id=?
    """, (referral_id, hospital_user_id))
    changed = cur.rowcount > 0
    conn.commit()
    conn.close()
    flash("Referral confirmed successfully." if changed else "Referral not found.", "success" if changed else "error")
    return redirect(url_for("dashboard.home"))


@admin_bp.route("/referrals/<int:referral_id>/pay", methods=["POST"])
@login_required(role="hospital")
def pay_referral(referral_id):
    payout_amount = (request.form.get("payout_amount") or "").strip()
    try:
        payout_amount_value = round(float(payout_amount), 2)
    except ValueError:
        payout_amount_value = -1

    if payout_amount_value <= 0:
        flash("Enter a valid payout amount greater than zero.", "error")
        return redirect(url_for("dashboard.home"))

    conn = get_conn()
    cur = conn.cursor()
    hospital_user_id = session.get("user_id")

    cur.execute("""
        SELECT r.id, r.lead_id, r.patient_name, d.phone AS doctor_phone
        FROM referrals r
        JOIN users d ON d.id = r.doctor_user_id
        WHERE r.id=? AND r.hospital_user_id=?
    """, (referral_id, hospital_user_id))
    row = cur.fetchone()
    if not row:
        conn.close()
        flash("Referral not found.", "error")
        return redirect(url_for("dashboard.home"))

    cur.execute("""
        UPDATE referrals
        SET referral_status=CASE WHEN referral_status='pending' THEN 'confirmed' ELSE referral_status END,
            payout_status='paid',
            payout_amount=?,
            approved_at=COALESCE(approved_at, CURRENT_TIMESTAMP),
            paid_at=CURRENT_TIMESTAMP,
            updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (payout_amount_value, referral_id))
    conn.commit()
    conn.close()

    queue_referral_paid_message(row["lead_id"], row["doctor_phone"], row["patient_name"])
    maybe_process_pending_notifications(limit=5)
    flash("Referral payout marked as paid.", "success")
    return redirect(url_for("dashboard.home"))


@admin_bp.route("/notifications/process", methods=["POST"])
@login_required(role="admin")
def process_notification_queue():
    processed = process_pending_notifications(limit=25)
    flash(f"Processed {processed} queued notification(s).", "success")
    return redirect(url_for("dashboard.home") + "#message-section")


def is_safe_readonly_query(query: str) -> bool:
    q = query.strip().lower()

    if not q:
        return False

    # only allow select / pragma(table_info) / explain query plan select
    allowed_starts = (
        "select",
        "pragma table_info(",
        "pragma_table_info(",
        "explain query plan select"
    )

    if not q.startswith(allowed_starts):
        return False

    blocked_keywords = [
        "insert",
        "update",
        "delete",
        "drop",
        "alter",
        "create",
        "replace",
        "truncate",
        "attach",
        "detach",
        "vacuum",
        "reindex",
        "grant",
        "revoke",
        "commit",
        "rollback",
        "savepoint",
        "release",
    ]

    for keyword in blocked_keywords:
        if re.search(rf"\b{keyword}\b", q):
            return False

    # block multiple statements
    if ";" in query.strip().rstrip(";"):
        return False

    return True


@admin_bp.route("/run-query", methods=["POST"])
@login_required(role="admin")
def run_query():
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()

    if not query:
        return jsonify({"error": "Empty query"}), 400

    if not is_safe_readonly_query(query):
        return jsonify({
            "error": "Only read-only SELECT queries are allowed in this SQL console."
        }), 400

    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute(query)

        if cur.description:
            columns = [desc[0] for desc in cur.description]
            rows = [dict(row) for row in cur.fetchall()]
        else:
            columns = []
            rows = []

        conn.close()
        return jsonify({
            "results": [
                {
                    "type": "select",
                    "columns": columns,
                    "rows": rows
                }
            ]
        })

    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 400