"""
Sends the alert emails for the scheduled runs (step 6).

After every step of a run, Airflow calls send_email: "OK" with what the
script printed, or "FAILED" with the error. The email goes out through
Gmail's mail server, logged in with a Gmail app password.

Settings (all in settings.py, set as environment variables):
ALERT_EMAIL_FROM, ALERT_EMAIL_PASSWORD, ALERT_EMAIL_TO, SMTP_HOST, SMTP_PORT
"""

import smtplib
from email.message import EmailMessage

from settings import ALERT_EMAIL_FROM, ALERT_EMAIL_PASSWORD, ALERT_EMAIL_TO, SMTP_HOST, SMTP_PORT


def send_email(subject, body):
    settings = {
        "ALERT_EMAIL_FROM": ALERT_EMAIL_FROM,
        "ALERT_EMAIL_PASSWORD": ALERT_EMAIL_PASSWORD,
        "ALERT_EMAIL_TO": ALERT_EMAIL_TO,
    }
    missing = [name for name, value in settings.items() if not value]
    if missing:
        raise RuntimeError(f"Can't send the alert email. Not set: {', '.join(missing)}")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = ALERT_EMAIL_FROM
    message["To"] = ALERT_EMAIL_TO
    message.set_content(body)

    # SMTP_SSL: the connection is encrypted from the start (port 465)
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
        server.login(ALERT_EMAIL_FROM, ALERT_EMAIL_PASSWORD)
        server.send_message(message)
