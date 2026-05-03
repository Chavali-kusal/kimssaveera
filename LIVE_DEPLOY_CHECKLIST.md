# Live deployment checklist

1. Do not upload local `database/healthqr.db`, `private_uploads/`, `__pycache__/`, or test PDFs/images to public hosting.
2. Set `APP_ENV=production` and a long random `SECRET_KEY` in environment variables.
3. Use HTTPS domain in `BASE_URL`.
4. Put database and private uploads outside public/static folders.
5. Run behind a production WSGI server such as gunicorn using `wsgi:app`.
6. Test routes: `/login`, `/doctor-signup`, `/m/login`, `/health`.
7. Use different browsers/profiles when testing admin, hospital and doctor at the same time; one browser profile has one active session.
8. Android/Mac browser cannot read SIM number. Only Android APK WebView can auto-pick if it provides `window.AndroidApp.getPhoneNumber()` or `getPhoneNumbers()`. Manual entry fallback is included.
