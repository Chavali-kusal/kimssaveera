import requests
import os

MSG91_AUTH_KEY = os.getenv("MSG91_AUTH_KEY")

def send_sms(mobile, message):
    try:
        url = "https://control.msg91.com/api/v5/flow/"

        payload = {
            "flow_id": "YOUR_FLOW_ID",   # we will set next
            "sender": "KIMSAV",          # any 6 letter name
            "mobiles": f"91{mobile}",
            "message": message
        }

        headers = {
            "authkey": MSG91_AUTH_KEY,
            "Content-Type": "application/json"
        }

        response = requests.post(url, json=payload, headers=headers)

        print("MSG91 Response:", response.text)

    except Exception as e:
        print("MSG91 Error:", e)