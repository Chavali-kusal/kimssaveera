import os
import re
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models.database import get_conn
from config import DOCTOR_DOCS_FOLDER
from utils.notifications import queue_doctor_registration_message
from utils.sms_service import maybe_process_pending_notifications

auth_bp = Blueprint("auth", __name__)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UPLOAD_FOLDER = DOCTOR_DOCS_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def is_valid_email(email):
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) is not None


def is_valid_pan(pan):
    return re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$", pan.upper()) is not None


def is_valid_aadhar(aadhar):
    if not aadhar:
        return True
    return len(aadhar) == 12 and aadhar.isdigit()


def is_valid_ifsc(ifsc):
    return re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", ifsc.upper()) is not None


def verify_stored_value(plain_value, stored_value):
    """
    Supports both:
    1. new hashed values
    2. old plain-text values (for migration compatibility)
    """
    if not plain_value or not stored_value:
        return False

    try:
        if check_password_hash(stored_value, plain_value):
            return True
    except Exception:
        pass

    return plain_value == stored_value


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        role = request.form.get("role", "").strip()
        login_input = request.form.get("login_input", "").strip()
        password = request.form.get("password", "").strip()
        secret_code = request.form.get("secret_code", "").strip()
        login_method = request.form.get("login_method", "password").strip().lower()

        if not role or not login_input:
            flash("Please select role and enter login details.", "error")
            return render_template("auth/login.html")

        if login_method == "password":
            secret_code = ""
            if not password:
                flash("Please enter password.", "error")
                return render_template("auth/login.html")
        elif login_method == "secret_code":
            password = ""
            if not secret_code:
                flash("Please enter secret code.", "error")
                return render_template("auth/login.html")
        else:
            flash("Invalid login method selected.", "error")
            return render_template("auth/login.html")

        conn = get_conn()
        cur = conn.cursor()

        if role == "doctor":
            cur.execute("""
                SELECT *
                FROM users
                WHERE role='doctor' AND (phone=? OR login_id=?)
            """, (login_input, login_input))
            user = cur.fetchone()

            if not user:
                conn.close()
                flash("Doctor account not found.", "error")
                return render_template("auth/login.html")

            if user["approval_status"] == "pending":
                conn.close()
                flash("Your registration is under admin verification.", "warning")
                return render_template("auth/login.html")

            if user["approval_status"] == "rejected":
                conn.close()
                flash("Your doctor account was rejected. Please contact admin.", "error")
                return render_template("auth/login.html")

            if int(user["is_active"]) != 1:
                conn.close()
                flash("Your account is inactive. Please contact admin.", "error")
                return render_template("auth/login.html")

            password_ok = verify_stored_value(password, user["password"]) if password else False
            secret_ok = verify_stored_value(secret_code, user["secret_code"]) if secret_code else False

            if password_ok or secret_ok:
                session.clear()
                session["user_id"] = user["id"]
                session["role"] = user["role"]
                session["display_name"] = user["display_name"]
                session["login_context"] = "web"
                conn.close()
                flash("Doctor login successful.", "success")
                return redirect(url_for("dashboard.home"))

            conn.close()
            flash("Invalid doctor credentials.", "error")
            return render_template("auth/login.html")

        elif role == "hospital":
            cur.execute("""
                SELECT *
                FROM users
                WHERE role='hospital' AND (hospital_name=? OR login_id=?)
            """, (login_input, login_input))
            user = cur.fetchone()

            if not user:
                conn.close()
                flash("Hospital account not found.", "error")
                return render_template("auth/login.html")

            if int(user["is_active"]) != 1:
                conn.close()
                flash("Hospital account is inactive. Please contact admin.", "error")
                return render_template("auth/login.html")

            password_ok = verify_stored_value(password, user["password"]) if password else False
            secret_ok = verify_stored_value(secret_code, user["secret_code"]) if secret_code else False

            if password_ok or secret_ok:
                session.clear()
                session["user_id"] = user["id"]
                session["role"] = user["role"]
                session["display_name"] = user["hospital_name"] or user["display_name"]
                session["login_context"] = "web"
                conn.close()
                flash("Hospital login successful.", "success")
                return redirect(url_for("dashboard.home"))

            conn.close()
            flash("Invalid hospital credentials.", "error")
            return render_template("auth/login.html")

        elif role == "admin":
            cur.execute("""
                SELECT *
                FROM users
                WHERE role='admin' AND (display_name=? OR login_id=?)
            """, (login_input, login_input))
            user = cur.fetchone()

            if not user:
                conn.close()
                flash("Admin account not found.", "error")
                return render_template("auth/login.html")

            if int(user["is_active"]) != 1:
                conn.close()
                flash("Admin account is inactive.", "error")
                return render_template("auth/login.html")

            password_ok = verify_stored_value(password, user["password"]) if password else False
            secret_ok = verify_stored_value(secret_code, user["secret_code"]) if secret_code else False

            if password_ok or secret_ok:
                session.clear()
                session["user_id"] = user["id"]
                session["role"] = user["role"]
                session["display_name"] = user["display_name"]
                session["login_context"] = "web"
                conn.close()
                flash("Admin login successful.", "success")
                return redirect(url_for("dashboard.home"))

            conn.close()
            flash("Invalid admin credentials.", "error")
            return render_template("auth/login.html")

        conn.close()
        flash("Please select valid role.", "error")

    return render_template("auth/login.html")


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        role = request.form.get("role", "").strip()
        login_input = request.form.get("login_input", "").strip()
        secret_code = request.form.get("secret_code", "").strip()
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not all([role, login_input, secret_code, new_password, confirm_password]):
            flash("Please fill all fields.", "error")
            return render_template("auth/forgot_password.html")

        if len(new_password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("auth/forgot_password.html")

        if new_password != confirm_password:
            flash("New password and confirm password do not match.", "error")
            return render_template("auth/forgot_password.html")

        conn = get_conn()
        cur = conn.cursor()

        if role == "doctor":
            cur.execute("""
                SELECT *
                FROM users
                WHERE role='doctor' AND (phone=? OR login_id=?)
            """, (login_input, login_input))
        elif role == "hospital":
            cur.execute("""
                SELECT *
                FROM users
                WHERE role='hospital' AND (hospital_name=? OR login_id=?)
            """, (login_input, login_input))
        elif role == "admin":
            cur.execute("""
                SELECT *
                FROM users
                WHERE role='admin' AND (display_name=? OR login_id=?)
            """, (login_input, login_input))
        else:
            conn.close()
            flash("Invalid role selected.", "error")
            return render_template("auth/forgot_password.html")

        user = cur.fetchone()

        if not user:
            conn.close()
            flash("Account not found.", "error")
            return render_template("auth/forgot_password.html")

        if not verify_stored_value(secret_code, user["secret_code"]):
            conn.close()
            flash("Invalid secret code.", "error")
            return render_template("auth/forgot_password.html")

        hashed_password = generate_password_hash(new_password)

        cur.execute(
            "UPDATE users SET password=? WHERE id=?",
            (hashed_password, user["id"])
        )
        conn.commit()
        conn.close()

        flash("Password reset successful. Please login.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html")


@auth_bp.route("/doctor-signup", methods=["GET", "POST"])
def doctor_signup_page():
    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        gender = request.form.get("gender", "").strip()
        registered_as = request.form.get("registered_as", "").strip()

        address = request.form.get("address", "").strip()
        city_name = request.form.get("city_name", "").strip()
        pincode = request.form.get("pincode", "").strip()

        pan_number = request.form.get("pan_number", "").strip().upper()
        aadhar_number = request.form.get("aadhar_number", "").strip()

        account_number = request.form.get("account_number", "").strip()
        ifsc_code = request.form.get("ifsc_code", "").strip().upper()
        upi_id = request.form.get("upi_id", "").strip()

        login_id = request.form.get("login_id", "").strip()
        password = request.form.get("password", "").strip()
        secret_code = request.form.get("secret_code", "").strip()
        organization_name = request.form.get("organization_name", "").strip()
        agree_terms = request.form.get("agree_terms")

        pan_file = request.files.get("pan_file")
        aadhar_file = request.files.get("aadhar_file")

        required_values = [
            display_name, phone, email, gender, registered_as,
            address, city_name, pincode,
            pan_number, account_number, ifsc_code, upi_id,
            login_id, password, secret_code, organization_name
        ]

        if not all(required_values) or not agree_terms:
            flash("Please fill all required fields.", "error")
            return render_template("auth/doctor_signup.html")

        if len(phone) != 10 or not phone.isdigit():
            flash("Mobile number must be 10 digits.", "error")
            return render_template("auth/doctor_signup.html")

        if login_id != phone:
            flash("Login ID must be same as mobile number.", "error")
            return render_template("auth/doctor_signup.html")

        if not is_valid_email(email):
            flash("Please enter valid email address.", "error")
            return render_template("auth/doctor_signup.html")

        if len(pincode) != 6 or not pincode.isdigit():
            flash("Pincode must be 6 digits.", "error")
            return render_template("auth/doctor_signup.html")

        if not is_valid_pan(pan_number):
            flash("Please enter valid PAN number.", "error")
            return render_template("auth/doctor_signup.html")

        if not is_valid_aadhar(aadhar_number):
            flash("Aadhaar number must be 12 digits.", "error")
            return render_template("auth/doctor_signup.html")

        if not is_valid_ifsc(ifsc_code):
            flash("Please enter valid IFSC code.", "error")
            return render_template("auth/doctor_signup.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("auth/doctor_signup.html")

        if len(secret_code) < 4:
            flash("Secret code must be at least 4 characters.", "error")
            return render_template("auth/doctor_signup.html")

        if not pan_file or pan_file.filename == "":
            flash("PAN proof is required.", "error")
            return render_template("auth/doctor_signup.html")

        if not allowed_file(pan_file.filename):
            flash("PAN file must be png, jpg, jpeg, or pdf.", "error")
            return render_template("auth/doctor_signup.html")

        if aadhar_file and aadhar_file.filename and not allowed_file(aadhar_file.filename):
            flash("Aadhaar file must be png, jpg, jpeg, or pdf.", "error")
            return render_template("auth/doctor_signup.html")

        conn = get_conn()
        cur = conn.cursor()

        cur.execute(
            "SELECT id FROM users WHERE phone=? OR email=? OR login_id=? OR pan_number=?",
            (phone, email, login_id, pan_number)
        )
        existing = cur.fetchone()

        if existing:
            conn.close()
            flash("Doctor account already exists with same mobile, email, login ID, or PAN.", "error")
            return render_template("auth/doctor_signup.html")

        pan_filename = ""
        aadhar_filename = ""
        saved_paths = []

        if pan_file:
            pan_file.stream.seek(0, os.SEEK_END)
            pan_size = pan_file.stream.tell()
            pan_file.stream.seek(0)
            if pan_size > 8 * 1024 * 1024:
                conn.close()
                flash("PAN file size must be below 8 MB.", "error")
                return render_template("auth/doctor_signup.html")

        if aadhar_file and aadhar_file.filename:
            aadhar_file.stream.seek(0, os.SEEK_END)
            aadhar_size = aadhar_file.stream.tell()
            aadhar_file.stream.seek(0)
            if aadhar_size > 8 * 1024 * 1024:
                conn.close()
                flash("Aadhaar file size must be below 8 MB.", "error")
                return render_template("auth/doctor_signup.html")

        if pan_file and pan_file.filename:
            pan_filename = f"pan_{phone}_{secure_filename(pan_file.filename)}"

        if aadhar_file and aadhar_file.filename:
            aadhar_filename = f"aadhar_{phone}_{secure_filename(aadhar_file.filename)}"

        hashed_password = generate_password_hash(password)
        hashed_secret_code = generate_password_hash(secret_code)

        try:
            cur.execute("BEGIN")
            cur.execute("""
                INSERT INTO users (
                    role,
                    display_name,
                    phone,
                    email,
                    gender,
                    registered_as,
                    address,
                    city_name,
                    pincode,
                    pan_number,
                    aadhar_number,
                    pan_file,
                    aadhar_file,
                    account_number,
                    ifsc_code,
                    upi_id,
                    login_id,
                    password,
                    secret_code,
                    organization_name,
                    approval_status,
                    is_active,
                    qr_generated
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "doctor",
                display_name,
                phone,
                email,
                gender,
                registered_as,
                address,
                city_name,
                pincode,
                pan_number,
                aadhar_number,
                pan_filename,
                aadhar_filename,
                account_number,
                ifsc_code,
                upi_id,
                login_id,
                hashed_password,
                hashed_secret_code,
                organization_name,
                "pending",
                0,
                0
            ))

            if pan_file and pan_file.filename:
                pan_path = os.path.join(UPLOAD_FOLDER, pan_filename)
                pan_file.save(pan_path)
                saved_paths.append(pan_path)

            if aadhar_file and aadhar_file.filename:
                aadhar_path = os.path.join(UPLOAD_FOLDER, aadhar_filename)
                aadhar_file.save(aadhar_path)
                saved_paths.append(aadhar_path)

            conn.commit()
        except Exception as exc:
            conn.rollback()
            for path in saved_paths:
                if os.path.exists(path):
                    os.remove(path)
            conn.close()
            error_text = str(exc) or "Unknown database error"
            flash(f"Doctor signup not submitted. Error: {error_text}", "error")
            return render_template("auth/doctor_signup.html")

        conn.close()

        queue_doctor_registration_message(phone)
        maybe_process_pending_notifications(limit=5)
        flash("Doctor registration submitted successfully. Waiting for admin approval.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/doctor_signup.html")


@auth_bp.route("/learn-more")
def learn_more():
    return render_template("auth/learn_more.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("auth.login"))