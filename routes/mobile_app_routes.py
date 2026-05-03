from werkzeug.security import check_password_hash
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models.database import get_conn
from utils.helpers import login_required

mobile_bp = Blueprint("mobile", __name__, url_prefix="/m")


def verify_stored_value(plain_value, stored_value):
    if not plain_value or not stored_value:
        return False
    try:
        if check_password_hash(stored_value, plain_value):
            return True
    except Exception:
        pass
    return plain_value == stored_value


def _date_filter_sql(params):
    clauses = ["l.doctor_user_id = ?"]
    if request.args.get("from_date", "").strip():
        clauses.append("date(l.created_at) >= date(?)")
        params.append(request.args.get("from_date").strip())
    if request.args.get("to_date", "").strip():
        clauses.append("date(l.created_at) <= date(?)")
        params.append(request.args.get("to_date").strip())
    return " AND ".join(clauses)


def _doctor_referrals(user_id):
    params = [user_id]
    where_sql = _date_filter_sql(params)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT
            l.id,
            l.patient_name,
            l.patient_phone,
            l.disease_notes,
            l.referral_note,
            l.submit_latitude,
            l.submit_longitude,
            l.submit_accuracy,
            l.submit_location_status,
            l.location_captured_at,
            l.status,
            l.created_at,
            c.clinic_name,
            c.area,
            c.contact_number,
            h.hospital_name,
            h.display_name AS hospital_display_name,
            r.referral_status,
            r.payout_status,
            r.payout_amount,
            r.approved_at,
            r.paid_at
        FROM leads l
        JOIN clinics c ON c.id = l.clinic_id
        JOIN users h ON h.id = l.hospital_user_id
        LEFT JOIN referrals r ON r.lead_id = l.id
        WHERE {where_sql}
        ORDER BY l.id DESC
        """,
        params,
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def _get_doctor(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=? AND role='doctor'", (user_id,))
    user = cur.fetchone()
    conn.close()
    return user


def _get_referral(user_id, lead_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            l.id,
            l.patient_name,
            l.patient_phone,
            l.disease_notes,
            l.referral_note,
            l.submit_latitude,
            l.submit_longitude,
            l.submit_accuracy,
            l.submit_location_status,
            l.location_captured_at,
            l.status,
            l.created_at,
            c.clinic_name,
            c.area,
            c.contact_number,
            h.hospital_name,
            h.display_name AS hospital_display_name,
            h.phone AS hospital_phone,
            r.referral_status,
            r.payout_status,
            r.payout_amount,
            r.approved_at,
            r.paid_at,
            r.updated_at
        FROM leads l
        JOIN clinics c ON c.id = l.clinic_id
        JOIN users h ON h.id = l.hospital_user_id
        LEFT JOIN referrals r ON r.lead_id = l.id
        WHERE l.doctor_user_id=? AND l.id=?
        """,
        (user_id, lead_id),
    )
    row = cur.fetchone()
    conn.close()
    return row


def _summary(referrals):
    return {
        "total_referrals": len(referrals),
        "confirmed": sum(1 for r in referrals if (r["referral_status"] or "pending").lower() == "confirmed"),
        "paid": sum(1 for r in referrals if (r["payout_status"] or "unpaid").lower() == "paid"),
        "payout_total": sum(float(r["payout_amount"] or 0) for r in referrals),
        "hospitals": len({r["hospital_name"] for r in referrals if r["hospital_name"]}),
    }


@mobile_bp.route("/")
def mobile_home():
    if session.get("role") == "doctor":
        return redirect(url_for("mobile.dashboard"))
    return redirect(url_for("mobile.login"))


@mobile_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "").strip()
        secret_code = request.form.get("secret_code", "").strip()
        login_method = request.form.get("login_method", "secret_code").strip().lower()

        if not phone:
            flash("Please enter doctor mobile number.", "error")
            return render_template("mobile/login.html")

        if login_method == "password" and not password:
            flash("Please enter password.", "error")
            return render_template("mobile/login.html")

        if login_method == "secret_code" and not secret_code:
            flash("Please enter secret code.", "error")
            return render_template("mobile/login.html")

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM users
            WHERE role='doctor' AND (phone=? OR login_id=?)
            """,
            (phone, phone),
        )
        user = cur.fetchone()

        if not user:
            conn.close()
            flash("Doctor account not found.", "error")
            return render_template("mobile/login.html")

        if user["approval_status"] == "pending":
            conn.close()
            flash("Your registration is under admin verification.", "warning")
            return render_template("mobile/login.html")

        if user["approval_status"] == "rejected":
            conn.close()
            flash("Your doctor account was rejected. Please contact hospital/admin.", "error")
            return render_template("mobile/login.html")

        if int(user["is_active"]) != 1:
            conn.close()
            flash("Your account is inactive. Please contact hospital/admin.", "error")
            return render_template("mobile/login.html")

        password_ok = verify_stored_value(password, user["password"]) if password else False
        secret_ok = verify_stored_value(secret_code, user["secret_code"]) if secret_code else False

        if password_ok or secret_ok:
            session.clear()
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            session["display_name"] = user["display_name"]
            session["login_context"] = "doctor_mobile"
            conn.close()
            return redirect(url_for("mobile.dashboard"))

        conn.close()
        flash("Invalid doctor credentials.", "error")

    return render_template("mobile/login.html")


@mobile_bp.route("/dashboard")
@login_required("doctor")
def dashboard():
    referrals = _doctor_referrals(session.get("user_id"))
    data = _summary(referrals)
    recent_referrals = referrals[:5]
    return render_template("mobile/doctor_dashboard.html", referrals=recent_referrals, **data)


@mobile_bp.route("/people")
@login_required("doctor")
def people():
    referrals = _doctor_referrals(session.get("user_id"))
    data = _summary(referrals)
    return render_template("mobile/people.html", referrals=referrals, **data)


@mobile_bp.route("/referral/<int:lead_id>")
@login_required("doctor")
def referral_detail(lead_id):
    row = _get_referral(session.get("user_id"), lead_id)
    if not row:
        flash("Referral not found.", "error")
        return redirect(url_for("mobile.people"))
    return render_template("mobile/referral_detail.html", row=row)


@mobile_bp.route("/profile")
@login_required("doctor")
def profile():
    user = _get_doctor(session.get("user_id"))
    return render_template("mobile/profile.html", user=user)


@mobile_bp.route("/more")
@login_required("doctor")
def more():
    referrals = _doctor_referrals(session.get("user_id"))
    data = _summary(referrals)
    return render_template("mobile/more.html", **data)


@mobile_bp.route("/logout")
@login_required("doctor")
def app_logout():
    session.clear()
    return render_template("mobile/app_closed.html")


@mobile_bp.route("/referrals/pdf")
@login_required("doctor")
def referrals_pdf():
    referrals = _doctor_referrals(session.get("user_id"))
    return render_template("mobile/referrals_pdf.html", referrals=referrals)
