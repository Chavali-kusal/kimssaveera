# 🚀 Render Deployment Guide - kimssaveera_services

Complete step-by-step guide for deploying your Flask application to Render.

## Prerequisites

- GitHub account with repository access
- Render account (create at [render.com](https://render.com))
- Environment variables configured (see `.env.example`)

---

## Step 1: Create a Render Account

1. Go to [render.com](https://render.com)
2. Click **Sign up**
3. Choose "Sign up with GitHub" for easy integration
4. Authorize Render to access your GitHub account

---

## Step 2: Create a New Web Service

1. In Render Dashboard, click **New +**
2. Select **Web Service**
3. Choose **Connect a repository**

---

## Step 3: Connect Your GitHub Repository

1. Search for `kimssaveera` repository
2. Click **Connect**
3. Configure the following:

| Field | Value |
|-------|-------|
| **Name** | `kimssaveera_services` |
| **Environment** | Python 3 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn wsgi:app` |
| **Plan** | Starter (Free) or Pro |

---

## Step 4: Set Environment Variables

### In Render Dashboard:

1. Go to your service settings
2. Navigate to **Environment** tab
3. Add the following variables:

```env
SECRET_KEY=<generate-a-strong-secret-key>
BASE_URL=https://kimssaveera-services.onrender.com
APP_ENV=production

# MSG91 SMS Configuration
MSG91_AUTH_KEY=<your-msg91-auth-key>
MSG91_FLOW_ID=<your-msg91-flow-id>
MSG91_SENDER_ID=KIMSAV
AUTO_SEND_NOTIFICATIONS=true

# Database & Paths
DATABASE_PATH=database/healthqr.db
QR_FOLDER=qr_codes
DOCTOR_DOCS_FOLDER=private_uploads/doctor_docs

# Other Settings
DEFAULT_COUNTRY_CODE=+91
PORT=8000
```

### 🔐 Generating SECRET_KEY

Run this command locally to generate a secure key:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy the output and paste it as `SECRET_KEY` in Render.

---

## Step 5: Deploy

1. Click **Create Web Service**
2. Render will start building your app
3. Watch the **Logs** tab for build progress
4. Once deployed, you'll see: ✅ `Your service is live!`

---

## Step 6: Access Your Application

Your app will be live at:
```
https://kimssaveera-services.onrender.com
```

Health check endpoint:
```
https://kimssaveera-services.onrender.com/health
```

---

## Post-Deployment Configuration

### 1. Admin Panel Setup

1. Navigate to login page: `https://kimssaveera-services.onrender.com`
2. **Default credentials:**
   - Username: `admin`
   - Password: `admin123`
3. ⚠️ **CHANGE IMMEDIATELY** after first login

### 2. Create Hospital

1. Go to Admin Panel → **Create Hospital**
2. Enter hospital details
3. Doctors require admin approval to join

### 3. Configure MSG91 SMS

1. Get your MSG91 credentials from [msg91.com](https://msg91.com)
2. Create an SMS Flow that accepts variable `VAR1`
3. Add credentials to Render environment variables
4. Enable `AUTO_SEND_NOTIFICATIONS=true`

---

## Automatic Deployments

### Enable Auto-Deploy

Every time you push to the main branch:

1. Render automatically rebuilds your app
2. New version deploys to `https://kimssaveera-services.onrender.com`
3. No manual action needed!

### Disable Auto-Deploy (if needed)

1. Service settings → **Deploy**
2. Turn off **Auto-Deploy**

---

## Monitoring & Logs

### View Live Logs

1. Go to your service dashboard
2. Click **Logs** tab
3. Filter by:
   - Build logs
   - Deploy logs
   - Runtime logs

### Common Issues

| Issue | Solution |
|-------|----------|
| Build failed | Check `requirements.txt` syntax |
| App crashes on start | Verify `SECRET_KEY` is set |
| Database errors | Check `DATABASE_PATH` permissions |
| SMS not sending | Verify MSG91 credentials in environment |

---

## File Storage

### Persistent Disk (if needed)

Render free tier does not provide persistent storage. To add:

1. Service → Settings → **Disks**
2. Add new disk: `/var/data`
3. Update paths in `config.py`:
   ```python
   QR_FOLDER=/var/data/qr_codes
   DATABASE_PATH=/var/data/database/healthqr.db
   ```

---

## Database Backup

### Create PostgreSQL Database (Optional)

1. Render Dashboard → **New +** → **PostgreSQL**
2. Configure and create
3. Copy connection string
4. Add to environment:
   ```env
   DATABASE_URL=postgres://user:pass@host:5432/dbname
   ```

---

## Health Check Endpoint

Render automatically checks: `https://kimssaveera-services.onrender.com/health`

This returns `OK` if your app is healthy.

---

## Troubleshooting

### App keeps restarting?

1. Check logs for errors
2. Verify all environment variables are set
3. Ensure `SECRET_KEY` is configured

### Build fails?

1. Run locally: `pip install -r requirements.txt`
2. Check Python version compatibility
3. Review build logs in Render dashboard

### Database connection errors?

1. Verify `DATABASE_PATH` exists or create it
2. Check file permissions in environment
3. For SQLite, ensure `/database/` directory exists

### SMS not sending?

1. Verify MSG91 credentials are correct
2. Check MSG91 Flow ID exists
3. Ensure `AUTO_SEND_NOTIFICATIONS=true`

---

## Performance Tips

1. **Keep dependencies minimal** - Only what's needed
2. **Use Starter plan initially** - Upgrade if needed
3. **Monitor logs regularly** - Catch issues early
4. **Enable auto-deploy** - Stay up to date

---

## Security Best Practices

✅ **Do:**
- Store secrets in Render environment variables
- Use strong `SECRET_KEY`
- Enable HTTPS (automatic on Render)
- Change default admin credentials
- Keep dependencies updated

❌ **Don't:**
- Commit `.env` file
- Hardcode secrets in code
- Use default credentials in production
- Share environment variable values

---

## Support & Resources

- **Render Docs:** https://render.com/docs
- **Flask Docs:** https://flask.palletsprojects.com
- **Gunicorn Docs:** https://gunicorn.org
- **MSG91 Docs:** https://msg91.com/api

---

## Quick Reference Commands

### Local Testing Before Deployment

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export SECRET_KEY="your-secret-key"
export BASE_URL="http://127.0.0.1:5000"
export APP_ENV="development"

# Run locally with gunicorn
gunicorn wsgi:app --bind 0.0.0.0:8000

# Access at: http://127.0.0.1:8000
```

---

## Next Steps

1. ✅ Deploy to Render
2. ✅ Access your app
3. ✅ Change admin credentials
4. ✅ Configure hospitals & doctors
5. ✅ Set up MSG91 SMS
6. ✅ Monitor and maintain

**Your app is now live! 🎉**
