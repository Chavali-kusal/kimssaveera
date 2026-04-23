Deploy notes:
1. Copy .env.example to .env and fill SECRET_KEY and MSG91 values.
2. Start with: gunicorn wsgi:app
3. On Render, set BASE_URL=https://kimssaveera.onrender.com (or your custom domain after DNS is connected).
4. Admin login default: admin / admin123 (change immediately after first login).
5. Create hospitals only from Admin > Create Hospital. Doctor approval is controlled only by admin. Referral confirm/payment is controlled by hospital login.


MSG91 SMS setup:
1. Add MSG91_AUTH_KEY and MSG91_FLOW_ID to .env.
2. Create an MSG91 SMS Flow that accepts variable VAR1.
3. The app sends the full SMS body in VAR1 to the configured flow.
4. Keep AUTO_SEND_NOTIFICATIONS=true to auto-send queued SMS notifications.
