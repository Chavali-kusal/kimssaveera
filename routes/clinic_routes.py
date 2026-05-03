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


@clinic_bp.route("/api/pending-doctors/<int:hospital_id>")
@login_required(role="admin")
def pending_doctors(hospital_id):
    """
    Return only approved + active doctors who still need QR for the selected hospital.

    Correct rules:
    - Same doctor + same hospital already generated => do not show.
    - Same doctor + same hospital already generated => cannot generate again.
    - Same doctor + different/new hospital => show again.

    Source of truth is hospital-specific:
    1) doctor_hospital_qr.qr_generated = 1, OR
    2) clinics row with a real qr_file value.

    Empty/stale clinic rows without qr_file are NOT treated as generated.
    """
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
          AND LOWER(IFNULL(u.approval_status, '')) = 'approved'
          AND NOT EXISTS (
              SELECT 1
              FROM doctor_hospital_qr q
              LEFT JOIN users du ON du.id = q.doctor_user_id
              WHERE q.hospital_user_id = ?
                AND q.qr_generated = 1
                AND (
                    q.doctor_user_id = u.id
                    OR (IFNULL(du.phone, '') <> '' AND IFNULL(u.phone, '') <> '' AND du.phone = u.phone)
                    OR (IFNULL(du.pan_number, '') <> '' AND IFNULL(u.pan_number, '') <> '' AND UPPER(du.pan_number) = UPPER(u.pan_number))
                )
          )
          AND NOT EXISTS (
              SELECT 1
              FROM clinics c
              LEFT JOIN users cu ON cu.id = c.doctor_user_id
              WHERE c.hospital_user_id = ?
                AND IFNULL(c.qr_file, '') <> ''
                AND (
                    c.doctor_user_id = u.id
                    OR (IFNULL(cu.phone, '') <> '' AND IFNULL(u.phone, '') <> '' AND cu.phone = u.phone)
                    OR (IFNULL(cu.pan_number, '') <> '' AND IFNULL(u.pan_number, '') <> '' AND UPPER(cu.pan_number) = UPPER(u.pan_number))
                )
          )
        ORDER BY u.display_name COLLATE NOCASE
        """,
        (hospital_id, hospital_id),
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

    def render_create():
        return render_template("clinic/create.html", doctors=doctors, hospitals=hospitals)

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
            return render_create()

        if contact_number and (len(contact_number) != 10 or not contact_number.isdigit()):
            flash("Contact number must be 10 digits.", "error")
            conn.close()
            return render_create()

        cur.execute(
            """
            SELECT id, phone, pan_number
            FROM users
            WHERE id=? AND role='doctor' AND is_active=1 AND LOWER(IFNULL(approval_status, ''))='approved'
            """,
            (doctor_user_id,),
        )
        doctor_row = cur.fetchone()

        if not doctor_row:
            flash("Selected doctor is invalid or not approved.", "error")
            conn.close()
            return render_create()

        doctor_phone = (doctor_row["phone"] or "").strip()
        doctor_pan = (doctor_row["pan_number"] or "").strip().upper()

        def existing_generated_for_selected_hospital():
            """Return clinic id when QR is already generated for same doctor/same hospital."""
            cur.execute(
                """
                SELECT c.id
                FROM clinics c
                JOIN users u ON u.id = c.doctor_user_id
                WHERE c.hospital_user_id = ?
                  AND IFNULL(c.qr_file, '') <> ''
                  AND (
                        c.doctor_user_id = ?
                        OR (IFNULL(u.phone, '') <> '' AND ? <> '' AND u.phone = ?)
                        OR (IFNULL(UPPER(u.pan_number), '') <> '' AND ? <> '' AND UPPER(u.pan_number) = ?)
                  )
                ORDER BY c.id DESC
                LIMIT 1
                """,
                (hospital_user_id, doctor_user_id, doctor_phone, doctor_phone, doctor_pan, doctor_pan),
            )
            row = cur.fetchone()
            if row:
                return row["id"]

            cur.execute(
                """
                SELECT COALESCE(c.id, q.id) AS existing_id
                FROM doctor_hospital_qr q
                LEFT JOIN clinics c
                  ON c.doctor_user_id = q.doctor_user_id
                 AND c.hospital_user_id = q.hospital_user_id
                LEFT JOIN users u ON u.id = q.doctor_user_id
                WHERE q.hospital_user_id = ?
                  AND q.qr_generated = 1
                  AND (
                        q.doctor_user_id = ?
                        OR (IFNULL(u.phone, '') <> '' AND ? <> '' AND u.phone = ?)
                        OR (IFNULL(UPPER(u.pan_number), '') <> '' AND ? <> '' AND UPPER(u.pan_number) = ?)
                  )
                ORDER BY existing_id DESC
                LIMIT 1
                """,
                (hospital_user_id, doctor_user_id, doctor_phone, doctor_phone, doctor_pan, doctor_pan),
            )
            row = cur.fetchone()
            return row["existing_id"] if row and row["existing_id"] else None

        def stale_unfinished_clinic_id():
            """Reuse unfinished row if previous attempt inserted clinic but qr_file was not saved."""
            cur.execute(
                """
                SELECT id
                FROM clinics
                WHERE doctor_user_id=?
                  AND hospital_user_id=?
                  AND IFNULL(qr_file, '') = ''
                ORDER BY id DESC
                LIMIT 1
                """,
                (doctor_user_id, hospital_user_id),
            )
            row = cur.fetchone()
            return row["id"] if row else None

        existing_id = existing_generated_for_selected_hospital()
        if existing_id:
            conn.close()
            flash("QR already generated for this doctor in the selected hospital.", "error")
            return redirect(url_for("clinic.created", clinic_id=existing_id))

        token = secrets.token_urlsafe(16)
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            conn.execute("BEGIN IMMEDIATE")

            existing_locked = existing_generated_for_selected_hospital()
            if existing_locked:
                conn.rollback()
                conn.close()
                flash("QR already generated for this doctor in the selected hospital.", "error")
                return redirect(url_for("clinic.created", clinic_id=existing_locked))

            stale_id = stale_unfinished_clinic_id()
            if stale_id:
                clinic_id = stale_id
                cur.execute(
                    """
                    UPDATE clinics
                    SET token=?, clinic_name=?, area=?, upi_id=?, contact_number=?, created_at=?
                    WHERE id=?
                    """,
                    (token, clinic_name, area, upi_id, contact_number, created_at, clinic_id),
                )
            else:
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
                    (token, doctor_user_id, hospital_user_id, clinic_name, area, upi_id, contact_number, "", created_at),
                )
                clinic_id = cur.lastrowid

            cur.execute(
                """
                INSERT OR REPLACE INTO doctor_hospital_qr(
                    id,
                    doctor_user_id,
                    hospital_user_id,
                    qr_generated,
                    qr_generated_at
                )
                VALUES(
                    (SELECT id FROM doctor_hospital_qr WHERE doctor_user_id=? AND hospital_user_id=?),
                    ?,?,?,?
                )
                """,
                (doctor_user_id, hospital_user_id, doctor_user_id, hospital_user_id, 1, created_at),
            )

            cur.execute(
                "UPDATE users SET qr_generated=1 WHERE id=? AND role='doctor'",
                (doctor_user_id,),
            )

            conn.commit()

        except sqlite3.IntegrityError:
            conn.rollback()
            existing_after_fail = existing_generated_for_selected_hospital()
            conn.close()

            if existing_after_fail:
                flash("QR already generated for this doctor in the selected hospital.", "error")
                return redirect(url_for("clinic.created", clinic_id=existing_after_fail))

            flash("Could not create clinic QR due to duplicate data. Please refresh and try again.", "error")
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

    lead_url = f"{BASE_URL}{url_for('clinic.scan_qr', token=row['token'])}"
    qr_file = f"clinic_{clinic_id}.png"
    qr_path = os.path.join(QR_FOLDER, qr_file)

    # Always regenerate the QR image with current BASE_URL so old localhost QR files are corrected on live.
    generate_qr_png(lead_url, qr_path)

    conn = get_conn()
    conn.execute("UPDATE clinics SET qr_file=? WHERE id=?", (qr_file, clinic_id))
    conn.commit()
    conn.close()

    return render_template("clinic/created.html", clinic=row, lead_url=lead_url, qr_file=qr_file)