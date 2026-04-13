
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
import random
import os
from django.conf import settings

def generate_otp():
    return str(random.randint(100000, 999999))

def send_api_email(to_email, subject, html_content, sender_name="Edu Village", sender_email=None):
    try:
        api_key = os.getenv("BREVO_API_KEY")
        if not sender_email:
            sender_email = os.getenv("DEFAULT_FROM_EMAIL")

        if not api_key:
            print("❌ Brevo API ERROR: API Key not found in environment!")
            return False

        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key['api-key'] = api_key

        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
            sib_api_v3_sdk.ApiClient(configuration)
        )

        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            to=[{"email": to_email}],
            sender={
                "email": sender_email,
                "name": sender_name
                },
            subject=subject,
            html_content=html_content
        )

        response = api_instance.send_transac_email(send_smtp_email)
        print(f"🚀 [Brevo API] Email sent to {to_email} | MessageID: {response.message_id}")
        return True

    except ApiException as e:
        print(f"🚨 [Brevo API Exception] Status: {e.status} | Reason: {e.reason} | Body: {e.body}")
        return False
    except Exception as e:
        print(f"🚨 [General Email Error] {e}")
        return False

def send_otp_email(to_email, otp):
    subject = "Your Verification Code"
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body {{ margin: 0; padding: 0; background: #0f172a; font-family: 'Segoe UI', sans-serif; }}
  .wrapper {{ width: 100%; padding: 40px 0; }}
  .card {{ max-width: 500px; margin: auto; background: linear-gradient(145deg, #0f172a, #1e293b); border-radius: 16px; padding: 30px; text-align: center; box-shadow: 0 0 25px rgba(34, 197, 94, 0.15); border: 1px solid rgba(255,255,255,0.05); }}
  .brand {{ color: #22c55e; font-size: 24px; font-weight: bold; margin-bottom: 20px; letter-spacing: 1px; }}
  h2 {{ color: #e2e8f0; margin-bottom: 10px; }}
  p {{ color: #94a3b8; font-size: 14px; }}
  .otp-box {{ margin: 25px 0; padding: 18px; font-size: 32px; letter-spacing: 10px; font-weight: bold; color: #22c55e; background: rgba(34,197,94,0.08); border: 1px solid rgba(34,197,94,0.3); border-radius: 12px; box-shadow: 0 0 20px rgba(34,197,94,0.2); }}
  .timer {{ color: #facc15; font-size: 13px; margin-top: 10px; }}
  .footer {{ margin-top: 30px; font-size: 12px; color: #64748b; line-height: 1.5; }}
</style>
</head>
<body>
  <div class="wrapper">
    <div class="card">
      <div class="brand">⚡ EDU VILLAGE</div>
      <h2>Verification Code</h2>
      <p>Please enter the following code to verify your signup.</p>
      <div class="otp-box">{otp}</div>
      <div class="timer">⏱ Valid for 5 minutes</div>
      <div class="footer">
        Do not share this code with anyone for security reasons.<br>
        If you didn't request this, please ignore this email.
      </div>
    </div>
  </div>
</body>
</html>
"""
    return send_api_email(to_email, subject, html_content)
