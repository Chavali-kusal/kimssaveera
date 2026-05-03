import requests
import os

MSG91_AUTH_KEY = os.getenv("MSG91_AUTH_KEY")
MSG91_WA_TEMPLATE_ID = os.getenv("MSG91_WA_TEMPLATE_ID")

def send_whatsapp(mobile, name):
    url = "https://control.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/"

    payload = {
        "template_id": MSG91_WA_TEMPLATE_ID,
        "short_url": "0",
        "recipients": [
            {
                "mobiles": f"91{mobile}",
                "name": name
            }
        ]
    }

    headers = {
        "authkey": MSG91_AUTH_KEY,
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=payload, headers=headers)

    print("WhatsApp Response:", response.text)