from functools import wraps
from flask import session, redirect, url_for, flash


def login_required(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Please login first.", "error")
                return redirect(url_for("auth.login"))

            user_role = session.get("role")

            if role:
                allowed_roles = role if isinstance(role, (list, tuple, set)) else [role]

                if user_role not in allowed_roles:
                    flash("You do not have access to that page.", "error")
                    return redirect(url_for("dashboard.home"))

            return fn(*args, **kwargs)
        return wrapper
    return decorator