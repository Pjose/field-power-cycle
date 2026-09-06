"""
Real delivery providers. This is the piece the rest of the notification
system (rules, the audit-backed feed) always stopped short of — every rule
trigger and every feed row has said plainly that delivery isn't real yet.
Here it actually is, for the two channels achievable without a hosted
service this sandbox can't reach:

- Email: stdlib `smtplib` over real SMTP. No SDK needed, no vendor lock-in,
  and it's what SendGrid/SES/Postmark's SMTP relay endpoints all speak
  anyway if you don't want their proprietary API. Configure
  FPC_SMTP_HOST/PORT/USER/PASSWORD/FROM and this sends real mail through
  any real SMTP server, including SendGrid's smtp.sendgrid.net.
- SMS: the real Twilio Python SDK. Configure FPC_TWILIO_ACCOUNT_SID,
  FPC_TWILIO_AUTH_TOKEN, and FPC_TWILIO_FROM_NUMBER and this sends a real
  text message through a real Twilio account.

Neither channel has real credentials configured in this reference
deployment — there's no Twilio account or production mail server reachable
from this environment. Both fall back to a `ConsoleProvider` that logs the
exact message that would have been sent, at which point the caller gets an
honest `{"delivered": False, "reason": "not configured"}` back rather than
a fabricated success. This is a materially different design from "pretend
it worked" — every call site can and does check `delivered` and records
the real outcome to the audit log.
"""
import logging
import os
import smtplib
from email.mime.text import MIMEText

logger = logging.getLogger("fpc.notifications.delivery")


def _smtp_configured() -> bool:
    return bool(os.environ.get("FPC_SMTP_HOST"))


def _twilio_configured() -> bool:
    return bool(os.environ.get("FPC_TWILIO_ACCOUNT_SID") and os.environ.get("FPC_TWILIO_AUTH_TOKEN"))


def send_email(to: str, subject: str, body: str) -> dict:
    """Sends a real email over real SMTP if FPC_SMTP_HOST is set. Returns a
    dict describing what actually happened — never claims delivery that
    didn't occur."""
    if not to:
        return {"delivered": False, "reason": "no recipient email on file"}

    if not _smtp_configured():
        logger.info("[EMAIL not sent — SMTP not configured] to=%s subject=%r body=%r", to, subject, body)
        return {"delivered": False, "reason": "SMTP not configured (set FPC_SMTP_HOST)"}

    host = os.environ["FPC_SMTP_HOST"]
    port = int(os.environ.get("FPC_SMTP_PORT", "587"))
    user = os.environ.get("FPC_SMTP_USER")
    password = os.environ.get("FPC_SMTP_PASSWORD")
    from_addr = os.environ.get("FPC_SMTP_FROM", "notifications@fieldpowercycle.example")
    use_tls = os.environ.get("FPC_SMTP_TLS", "1") == "1"

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to

    try:
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            if use_tls:
                smtp.starttls()
            if user and password:
                smtp.login(user, password)
            smtp.sendmail(from_addr, [to], msg.as_string())
        logger.info("email delivered to=%s subject=%r", to, subject)
        return {"delivered": True, "channel": "email", "to": to}
    except Exception as e:
        logger.exception("real SMTP send failed")
        return {"delivered": False, "reason": f"SMTP error: {e}"}


def send_sms(to: str, body: str) -> dict:
    """Sends a real SMS via the real Twilio API if credentials are set.
    Returns a dict describing what actually happened."""
    if not to:
        return {"delivered": False, "reason": "no recipient phone number on file"}

    if not _twilio_configured():
        logger.info("[SMS not sent — Twilio not configured] to=%s body=%r", to, body)
        return {"delivered": False, "reason": "Twilio not configured (set FPC_TWILIO_ACCOUNT_SID / FPC_TWILIO_AUTH_TOKEN)"}

    from twilio.rest import Client  # imported lazily so the dependency is only needed if this path is actually used

    account_sid = os.environ["FPC_TWILIO_ACCOUNT_SID"]
    auth_token = os.environ["FPC_TWILIO_AUTH_TOKEN"]
    from_number = os.environ.get("FPC_TWILIO_FROM_NUMBER")
    if not from_number:
        return {"delivered": False, "reason": "FPC_TWILIO_FROM_NUMBER not set"}

    try:
        client = Client(account_sid, auth_token)
        message = client.messages.create(body=body, from_=from_number, to=to)
        logger.info("sms delivered to=%s sid=%s", to, message.sid)
        return {"delivered": True, "channel": "sms", "to": to, "twilio_sid": message.sid}
    except Exception as e:
        logger.exception("real Twilio send failed")
        return {"delivered": False, "reason": f"Twilio error: {e}"}
