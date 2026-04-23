from flask import Blueprint, render_template, session, request, redirect, url_for, flash
from models.database import get_conn
from utils.helpers import login_required
from utils.notifications import requeue_notification


dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


def _build_date_filters(column_name: str, params: list):
    clauses = []
    from_date = request.args.get("from_date", "").strip()
    to_date = request.args.get("to_date", "").strip()
    if from_date:
        clauses.append(f"date({column_name}) >= date(?)")
        params.append(from_date)
    if to_date:
        clauses.append(f"date({column_name}) <= date(?)")
        params.append(to_date)
    return clauses


@dashboard_bp.route("")
@login_required()
def home():
    user_id = session.get("user_id")
    role = session.get("role")

    leads = []
    clinics = []
    notifications = []
    hospital_summary = []
    registered_doctors = []

    conn = get_conn()
    cur = conn.cursor()

    if role == "doctor":
        params = [user_id]
        conditions = ["l.doctor_user_id = ?"]
        conditions.extend(_build_date_filters("l.created_at", params))
        lead_where = " AND ".join(conditions)

        cur.execute(
            f"""
            SELECT
                l.*,
                c.clinic_name,
                u.display_name AS doctor_name,
                h.hospital_name,
                r.id AS referral_id,
                r.referral_status,
                r.payout_status,
                r.payout_amount,
                r.approved_at,
                r.paid_at
            FROM leads l
            JOIN clinics c ON c.id = l.clinic_id
            JOIN users u ON u.id = l.doctor_user_id
            JOIN users h ON h.id = l.hospital_user_id
            LEFT JOIN referrals r ON r.lead_id = l.id
            WHERE {lead_where}
            ORDER BY l.id DESC
            """,
            params,
        )
        leads = cur.fetchall()

        cur.execute(
            """
            SELECT c.*, h.hospital_name
            FROM clinics c
            JOIN users h ON h.id = c.hospital_user_id
            WHERE c.doctor_user_id = ?
            ORDER BY c.id DESC
            """,
            (user_id,),
        )
        clinics = cur.fetchall()

        cur.execute(
            """
            SELECT h.hospital_name, COUNT(l.id) AS total_patients
            FROM leads l
            JOIN users h ON h.id = l.hospital_user_id
            WHERE l.doctor_user_id = ?
            GROUP BY h.hospital_name
            ORDER BY total_patients DESC, h.hospital_name
            """,
            (user_id,),
        )
        hospital_summary = cur.fetchall()

        cur.execute(
            """
            SELECT n.*, l.patient_name
            FROM notifications n
            LEFT JOIN leads l ON l.id = n.lead_id
            WHERE LOWER(COALESCE(n.recipient_role, '')) IN ('doctor', 'doctor_registration', 'doctor_approval', 'doctor_payout')
              AND n.recipient_value = (SELECT COALESCE(phone, '') FROM users WHERE id = ?)
            ORDER BY n.id DESC
            LIMIT 20
            """,
            (user_id,),
        )
        notifications = cur.fetchall()

    elif role == "hospital":
        params = [user_id]
        conditions = ["l.hospital_user_id = ?"]
        conditions.extend(_build_date_filters("l.created_at", params))
        lead_where = " AND ".join(conditions)

        cur.execute(
            f"""
            SELECT
                l.*,
                c.clinic_name,
                u.display_name AS doctor_name,
                h.hospital_name,
                r.id AS referral_id,
                r.referral_status,
                r.payout_status,
                r.payout_amount,
                r.approved_at,
                r.paid_at
            FROM leads l
            JOIN clinics c ON c.id = l.clinic_id
            JOIN users u ON u.id = l.doctor_user_id
            JOIN users h ON h.id = l.hospital_user_id
            LEFT JOIN referrals r ON r.lead_id = l.id
            WHERE {lead_where}
            ORDER BY l.id DESC
            """,
            params,
        )
        leads = cur.fetchall()

        cur.execute(
            """
            SELECT c.*, d.display_name AS doctor_name
            FROM clinics c
            JOIN users d ON d.id = c.doctor_user_id
            WHERE c.hospital_user_id = ?
            ORDER BY c.id DESC
            """,
            (user_id,),
        )
        clinics = cur.fetchall()

        cur.execute(
            """
            SELECT
                d.id,
                d.display_name,
                d.phone,
                d.email,
                d.city_name,
                d.organization_name,
                COUNT(DISTINCT c.id) AS total_clinics,
                COUNT(DISTINCT l.id) AS total_referrals
            FROM clinics c
            JOIN users d ON d.id = c.doctor_user_id
            LEFT JOIN leads l ON l.doctor_user_id = d.id AND l.hospital_user_id = c.hospital_user_id
            WHERE c.hospital_user_id = ?
            GROUP BY d.id, d.display_name, d.phone, d.email, d.city_name, d.organization_name
            ORDER BY d.display_name
            """,
            (user_id,),
        )
        registered_doctors = cur.fetchall()

        cur.execute(
            """
            SELECT n.*, l.patient_name
            FROM notifications n
            LEFT JOIN leads l ON l.id = n.lead_id
            WHERE LOWER(COALESCE(n.recipient_role, '')) = 'hospital'
              AND n.recipient_value = (
                  SELECT COALESCE(phone, '')
                  FROM users
                  WHERE id = ?
              )
            ORDER BY n.id DESC
            LIMIT 20
            """,
            (user_id,),
        )
        notifications = cur.fetchall()

    elif role == "admin":
        params = []
        conditions = ["1=1"]
        conditions.extend(_build_date_filters("l.created_at", params))

        status_filter = request.args.get("status_filter", "").strip().lower()
        if status_filter == "sent":
            conditions.append("UPPER(COALESCE(n.delivery_status, '')) = 'SENT'")
        elif status_filter == "pending":
            conditions.append("UPPER(COALESCE(n.delivery_status, '')) = 'QUEUED'")
        elif status_filter == "failed":
            conditions.append("UPPER(COALESCE(n.delivery_status, '')) = 'FAILED'")

        cur.execute(
            f"""
            SELECT
                l.*,
                c.clinic_name,
                d.display_name AS doctor_name,
                h.hospital_name,
                r.id AS referral_id,
                r.referral_status,
                r.payout_status,
                r.payout_amount,
                r.approved_at,
                r.paid_at
            FROM leads l
            JOIN clinics c ON c.id = l.clinic_id
            JOIN users d ON d.id = l.doctor_user_id
            JOIN users h ON h.id = l.hospital_user_id
            LEFT JOIN referrals r ON r.lead_id = l.id
            WHERE {' AND '.join([c for c in conditions if not c.startswith('UPPER(COALESCE(n.')])}
            ORDER BY l.id DESC
            """,
            [p for p in params],
        )
        leads = cur.fetchall()

        cur.execute(
            """
            SELECT c.*, d.display_name AS doctor_name, h.hospital_name
            FROM clinics c
            JOIN users d ON d.id = c.doctor_user_id
            JOIN users h ON h.id = c.hospital_user_id
            ORDER BY c.id DESC
            """
        )
        clinics = cur.fetchall()

        notification_params = []
        notification_conditions = ["LOWER(COALESCE(n.recipient_role, '')) = 'admin_team'"]
        notification_conditions.extend(_build_date_filters("n.created_at", notification_params))
        if status_filter == "sent":
            notification_conditions.append("UPPER(COALESCE(n.delivery_status, '')) = 'SENT'")
        elif status_filter == "pending":
            notification_conditions.append("UPPER(COALESCE(n.delivery_status, '')) = 'QUEUED'")
        elif status_filter == "failed":
            notification_conditions.append("UPPER(COALESCE(n.delivery_status, '')) = 'FAILED'")

        cur.execute(
            f"""
            SELECT n.*, l.patient_name
            FROM notifications n
            LEFT JOIN leads l ON l.id = n.lead_id
            WHERE {' AND '.join(notification_conditions)}
            ORDER BY n.id DESC
            LIMIT 50
            """,
            notification_params,
        )
        notifications = cur.fetchall()

    conn.close()

    return render_template(
        "dashboard/home.html",
        leads=leads,
        clinics=clinics,
        notifications=notifications,
        hospital_summary=hospital_summary,
        registered_doctors=registered_doctors,
        role=role,
    )


@dashboard_bp.post("/notifications/<int:notification_id>/resend")
@login_required("admin")
def resend_notification(notification_id):
    if requeue_notification(notification_id):
        flash("Failed message moved to pending for resend.", "success")
    else:
        flash("Message not found.", "error")
    return redirect(url_for("dashboard.home") + "#message-section")
