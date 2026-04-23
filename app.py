import os
from flask import Flask, request, send_from_directory, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from config import SECRET_KEY, QR_FOLDER, IS_PRODUCTION
from models.tables import init_db
from models.database import optimize_database
from routes.auth_routes import auth_bp
from routes.dashboard_routes import dashboard_bp
from routes.clinic_routes import clinic_bp
from routes.lead_routes import lead_bp
from routes.admin_routes import admin_bp
from routes.webhook_routes import webhook_bp


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = IS_PRODUCTION

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

    @app.get("/")
    def home():
        return redirect(url_for("auth.login"))

    @app.get("/health")
    def health():
        return "OK"

    @app.get("/qr/<path:filename>")
    def qr_view(filename):
        download = request.args.get("download") == "1"
        return send_from_directory(QR_FOLDER, filename, as_attachment=download)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
