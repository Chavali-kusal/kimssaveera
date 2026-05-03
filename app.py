import os
from datetime import timedelta
from flask import Flask, request, send_from_directory, redirect, url_for, render_template
from werkzeug.middleware.proxy_fix import ProxyFix
from config import SECRET_KEY, QR_FOLDER, IS_PRODUCTION, SESSION_COOKIE_SECURE
from models.tables import init_db
from models.database import optimize_database
from routes.auth_routes import auth_bp
from routes.dashboard_routes import dashboard_bp
from routes.clinic_routes import clinic_bp
from routes.lead_routes import lead_bp
from routes.admin_routes import admin_bp
from routes.webhook_routes import webhook_bp
from routes.mobile_app_routes import mobile_bp


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = SESSION_COOKIE_SECURE
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)

    if IS_PRODUCTION:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    os.makedirs(QR_FOLDER, exist_ok=True)

    init_db()
    optimize_database()

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(clinic_bp)
    app.register_blueprint(lead_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(webhook_bp)
    app.register_blueprint(mobile_bp)

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(self), camera=(), microphone=()")
        if IS_PRODUCTION:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    @app.get("/")
    def home():
        """
        Smart entry point:
        - Windows desktop/laptop users go to the normal web login.
        - Android, iPhone, iPad, Mac, and other users go to the PWA/mobile login.
        """
        user_agent = request.headers.get("User-Agent", "").lower()

        if "windows" in user_agent:
            return redirect(url_for("auth.login"))

        return redirect(url_for("mobile.login"))

    @app.get("/choose")
    @app.get("/home_choice")
    def home_choice():
        """Manual login selector, useful if user wants to choose mobile or web manually."""
        return render_template("home_choice.html")

    @app.get("/health")
    def health():
        return "OK"

    @app.get("/manifest.json")
    def pwa_manifest():
        response = send_from_directory("static", "manifest.json", mimetype="application/manifest+json")
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/service-worker.js")
    def pwa_service_worker():
        response = send_from_directory("static", "service-worker.js", mimetype="application/javascript")
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/offline.html")
    def pwa_offline():
        return send_from_directory("static", "offline.html")

    @app.get("/qr/<path:filename>")
    def qr_view(filename):
        download = request.args.get("download") == "1"
        return send_from_directory(QR_FOLDER, filename, as_attachment=download)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
