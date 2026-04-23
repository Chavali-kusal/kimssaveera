import os
import secrets
import sqlite3
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from config import QR_FOLDER, BASE_URL
from models.database import get_conn
from utils.helpers import login_required
from utils.qr_generator import generate_qr_png

clinic_bp = Blueprint("clinic", __name__, url_prefix="/clinic")


def _public_base_url() -> str:
    host_url = (request.host_url or "").strip()
    if host_url:
        return host_url.rstrip("/")
    return BASE_URL


@clinic_bp.route("/api/pending-doctors/<int:hospital_id>")
@login_required(role="admin")
def pending_doctors(hospital_id):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT u.id,
               u.display_name,
               u.phone,
               u.pan_number,
               u.organization_name,
               u.city_name,
               u.upi_id
        FROM users u
        WHERE u.role = 'doctor'
          AND u.is_active = 1
          AND u.approval_status = 'approved'
          AND NOT EXISTS (
              SELECT 1
              FROM doctor_hospital_qr q
              JOIN users du ON du.id = q.doctor_user_id
              WHERE q.hospital_user_id = ?
                AND q.qr_generated = 1
                AND (
                    q.doctor_user_id = u.id
                    OR (IFNULL(du.phone, '') <> '' AND du.phone = u.phone)
                    OR (IFNULL(du.pan_number, '') <> '' AND du.pan_number = u.pan_number)
                )
          )
        ORDER BY u.display_name
        """,
        (hospital_id,),
    )

    rows = cur.fetchall()
    conn.close()

    return jsonify([dict(r) for r in rows])


@clinic_bp.route("/create", methods=["GET", "POST"])
@login_required(role="admin")
def create_clinic():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, hospital_name
        FROM users
        WHERE role='hospital' AND is_active=1
        ORDER BY hospital_name
    """)
    hospitals = cur.fetchall()

    doctors = []

    if request.method == "POST":
        doctor_user_id = request.form.get("doctor_user_id", "").strip()
        hospital_user_id = request.form.get("hospital_user_id", "").strip()
        clinic_name = request.form.get("clinic_name", "").strip()
        area = request.form.get("area", "").strip()
        contact_number = request.form.get("contact_number", "").strip()
        upi_id = request.form.get("upi_id", "").strip()

        if not doctor_user_id or not hospital_user_id or not clinic_name:
            flash("Doctor, hospital, and clinic name are required.", "error")
            conn.close()
            return render_template("clinic/create.html", doctors=doctors, hospitals=hospitals)

        if contact_number and (len(contact_number) != 10 or not contact_number.isdigit()):
            flash("Contact number must be 10 digits.", "error")
            conn.close()
            return render_template("clinic/create.html", doctors=doctors, hospitals=hospitals)

        cur.execute(
            """
            SELECT id, phone, pan_number
            FROM users
            WHERE id=? AND role='doctor' AND is_active=1 AND approval_status='approved'
            """,
            (doctor_user_id,),
        )
        doctor_row = cur.fetchone()

        if not doctor_row:
            flash("Selected doctor is invalid or not approved.", "error")
            conn.close()
            return render_template("clinic/create.html", doctors=doctors, hospitals=hospitals)

        doctor_phone = (doctor_row["phone"] or "").strip()
        doctor_pan = (doctor_row["pan_number"] or "").strip().upper()

        # 1) direct duplicate by doctor + hospital
        cur.execute(
            """
            SELECT c.id
            FROM clinics c
            JOIN doctor_hospital_qr q
              ON q.doctor_user_id = c.doctor_user_id
             AND q.hospital_user_id = c.hospital_user_id
            WHERE c.doctor_user_id = ?
              AND c.hospital_user_id = ?
              AND q.qr_generated = 1
            LIMIT 1
            """,
            (doctor_user_id, hospital_user_id),
        )
        direct_existing = cur.fetchone()
        if direct_existing:
            clinic_id = direct_existing["id"]
            conn.close()
            flash("QR already generated for this doctor in selected hospital.", "error")
            return redirect(url_for("clinic.created", clinic_id=clinic_id))

        # 2) duplicate by same mobile in same hospital
        if doctor_phone:
            cur.execute(
                """
                SELECT c.id
                FROM clinics c
                JOIN users u ON u.id = c.doctor_user_id
                JOIN doctor_hospital_qr q
                  ON q.doctor_user_id = c.doctor_user_id
                 AND q.hospital_user_id = c.hospital_user_id
                WHERE c.hospital_user_id = ?
                  AND q.qr_generated = 1
                  AND u.role = 'doctor'
                  AND IFNULL(u.phone, '') = ?
                LIMIT 1
                """,
                (hospital_user_id, doctor_phone),
            )
            phone_existing = cur.fetchone()
            if phone_existing:
                clinic_id = phone_existing["id"]
                conn.close()
                flash("A QR already exists in this hospital for the same doctor mobile number.", "error")
                return redirect(url_for("clinic.created", clinic_id=clinic_id))

        # 3) duplicate by same PAN in same hospital
        if doctor_pan:
            cur.execute(
                """
                SELECT c.id
                FROM clinics c
                JOIN users u ON u.id = c.doctor_user_id
                JOIN doctor_hospital_qr q
                  ON q.doctor_user_id = c.doctor_user_id
                 AND q.hospital_user_id = c.hospital_user_id
                WHERE c.hospital_user_id = ?
                  AND q.qr_generated = 1
                  AND u.role = 'doctor'
                  AND UPPER(IFNULL(u.pan_number, '')) = ?
                LIMIT 1
                """,
                (hospital_user_id, doctor_pan),
            )
            pan_existing = cur.fetchone()
            if pan_existing:
                clinic_id = pan_existing["id"]
                conn.close()
                flash("A QR already exists in this hospital for the same doctor PAN number.", "error")
                return redirect(url_for("clinic.created", clinic_id=clinic_id))

        # 4) clinic duplicate check
        cur.execute(
            """
            SELECT id
            FROM clinics
            WHERE doctor_user_id = ?
              AND hospital_user_id = ?
              AND clinic_name = ?
              AND IFNULL(contact_number, '') = IFNULL(?, '')
            """,
            (doctor_user_id, hospital_user_id, clinic_name, contact_number),
        )
        row = cur.fetchone()

        if row:
            clinic_id = row["id"]
            conn.close()
            flash("Clinic already exists. Existing QR opened.", "success")
            return redirect(url_for("clinic.created", clinic_id=clinic_id))

        token = secrets.token_urlsafe(16)
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        qr_file = ""

        try:
            # transaction start
            conn.execute("BEGIN IMMEDIATE")

            # re-check inside transaction to prevent race condition
            cur.execute(
                """
                SELECT c.id
                FROM clinics c
                JOIN users u ON u.id = c.doctor_user_id
                LEFT JOIN doctor_hospital_qr q
                  ON q.doctor_user_id = c.doctor_user_id
                 AND q.hospital_user_id = c.hospital_user_id
                WHERE c.hospital_user_id = ?
                  AND (
                        c.doctor_user_id = ?
                        OR (IFNULL(u.phone, '') <> '' AND u.phone = ?)
                        OR (IFNULL(UPPER(u.pan_number), '') <> '' AND UPPER(u.pan_number) = ?)
                  )
                LIMIT 1
                """,
                (hospital_user_id, doctor_user_id, doctor_phone, doctor_pan),
            )
            existing_locked = cur.fetchone()
            if existing_locked:
                conn.rollback()
                clinic_id = existing_locked["id"]
                flash("QR already exists for this doctor/mobile/PAN in the selected hospital.", "error")
                return redirect(url_for("clinic.created", clinic_id=clinic_id))

            cur.execute(
                """
                INSERT INTO clinics(
                    token,
                    doctor_user_id,
                    hospital_user_id,
                    clinic_name,
                    area,
                    upi_id,
                    contact_number,
                    qr_file,
                    created_at
                )
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (token, doctor_user_id, hospital_user_id, clinic_name, area, upi_id, contact_number, qr_file, created_at),
            )
            clinic_id = cur.lastrowid

            cur.execute(
                """
                INSERT INTO doctor_hospital_qr(
                    doctor_user_id,
                    hospital_user_id,
                    qr_generated,
                    qr_generated_at
                )
                VALUES(?,?,?,?)
                """,
                (doctor_user_id, hospital_user_id, 1, created_at),
            )

            conn.commit()

        except sqlite3.IntegrityError:
            conn.rollback()

            cur.execute(
                """
                SELECT c.id
                FROM clinics c
                JOIN users u ON u.id = c.doctor_user_id
                WHERE c.hospital_user_id = ?
                  AND (
                        c.doctor_user_id = ?
                        OR (IFNULL(u.phone, '') <> '' AND u.phone = ?)
                        OR (IFNULL(UPPER(u.pan_number), '') <> '' AND UPPER(u.pan_number) = ?)
                  )
                LIMIT 1
                """,
                (hospital_user_id, doctor_user_id, doctor_phone, doctor_pan),
            )
            existing_after_fail = cur.fetchone()

            conn.close()

            if existing_after_fail:
                flash("QR already exists for this doctor/mobile/PAN in the selected hospital.", "error")
                return redirect(url_for("clinic.created", clinic_id=existing_after_fail["id"]))

            flash("Could not create clinic QR due to duplicate data.", "error")
            return render_template("clinic/create.html", doctors=doctors, hospitals=hospitals)

        except Exception:
            conn.rollback()
            conn.close()
            flash("Unexpected error while creating clinic QR.", "error")
            return render_template("clinic/create.html", doctors=doctors, hospitals=hospitals)

        conn.close()
        flash("Clinic QR created successfully.", "success")
        return redirect(url_for("clinic.created", clinic_id=clinic_id))

    conn.close()
    return render_template("clinic/create.html", doctors=doctors, hospitals=hospitals)


@clinic_bp.route("/scan/<token>")
def scan_qr(token):
    conn = get_conn()
    cur = conn.cursor()

    # Find clinic
    cur.execute("SELECT id FROM clinics WHERE token=?", (token,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return "Invalid QR", 404

    clinic_id = row["id"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Insert scan log
    cur.execute("""
        INSERT INTO qr_scans(clinic_id, scanned_at)
        VALUES(?, ?)
    """, (clinic_id, now))

    # Update counters
    cur.execute("""
        UPDATE clinics
        SET scan_count = COALESCE(scan_count, 0) + 1,
            last_scanned_at = ?
        WHERE id = ?
    """, (now, clinic_id))

    conn.commit()
    conn.close()

    return redirect(url_for("lead.lead_form", token=token))

@clinic_bp.route("/created/<int:clinic_id>")
@login_required(role="admin")
def created(clinic_id: int):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT c.*, d.display_name AS doctor_name, h.hospital_name
        FROM clinics c
        JOIN users d ON d.id = c.doctor_user_id
        JOIN users h ON h.id = c.hospital_user_id
        WHERE c.id = ?
        """,
        (clinic_id,),
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return "Clinic not found", 404

    lead_url = f"{_public_base_url()}{url_for('clinic.scan_qr', token=row['token'])}"
    qr_file = f"clinic_{clinic_id}.png"
    qr_path = os.path.join(QR_FOLDER, qr_file)

    if not os.path.exists(qr_path):
        generate_qr_png(lead_url, qr_path)

        conn = get_conn()
        conn.execute("UPDATE clinics SET qr_file=? WHERE id=?", (qr_file, clinic_id))
        conn.commit()
        conn.close()

    return render_template("clinic/created.html", clinic=row, lead_url=lead_url, qr_file=qr_file)