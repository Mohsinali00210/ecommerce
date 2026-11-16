"""Turn SMTP failures into a plain-English reason an administrator can fix.

Messages never include the password; they name the setting to change."""
import smtplib
import socket
import ssl

from django.conf import settings


def config_problem():
    """Problems visible without connecting."""
    backend = settings.EMAIL_BACKEND
    if "smtp" not in backend:
        return None  # console/locmem/file backends need no credentials
    if not settings.EMAIL_HOST_PASSWORD:
        return ("No email password is configured. Add SMTP_PASSWORD=<your mailbox password> to the .env "
                "file on the server and restart the site (it used to be inside settings.py).")
    if settings.EMAIL_USE_SSL and settings.EMAIL_USE_TLS:
        return "SMTP_USE_SSL and SMTP_USE_TLS are both on. Use SSL with port 465, or TLS with port 587."
    if not settings.EMAIL_HOST_USER:
        return "SMTP_USER (the mailbox to sign in with) is empty in .env."
    return None


def explain(exc):
    """Human reason for an exception raised while sending."""
    host = f"{settings.EMAIL_HOST}:{settings.EMAIL_PORT}"
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return (f"The mail server rejected the login for {settings.EMAIL_HOST_USER}. Check SMTP_USER and "
                f"SMTP_PASSWORD in .env (the password may have been changed in Hostinger).")
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return (f"The mail server refused to send as {settings.DEFAULT_FROM_EMAIL}. Set SMTP_FROM to the "
                f"same mailbox as SMTP_USER ({settings.EMAIL_HOST_USER}), or add it as an alias in Hostinger.")
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "The mail server refused the recipient address."
    if isinstance(exc, (smtplib.SMTPServerDisconnected,)) or isinstance(exc, ssl.SSLError):
        return (f"The connection to {host} was dropped. Port 465 needs SMTP_USE_SSL=True; "
                f"port 587 needs SMTP_USE_TLS=True (and SSL off).")
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return f"Timed out connecting to {host}. The server's firewall or hosting provider may block outgoing mail ports."
    if isinstance(exc, (ConnectionRefusedError, socket.gaierror, OSError)):
        return f"Couldn't connect to {host} ({type(exc).__name__}). Check SMTP_HOST / SMTP_PORT and outgoing firewall rules."
    if isinstance(exc, smtplib.SMTPException):
        return f"The mail server returned an error: {exc}"
    return f"{type(exc).__name__}: {exc}"


def send_test(to):
    """Returns (ok, message)."""
    problem = config_problem()
    if problem:
        return False, problem
    from django.core.mail import send_mail
    try:
        send_mail("Shan Zee test email", "Email sending works.", settings.DEFAULT_FROM_EMAIL, [to],
                  fail_silently=False)
    except Exception as exc:
        return False, explain(exc)
    return True, f"Test email sent to {to} from {settings.DEFAULT_FROM_EMAIL} via {settings.EMAIL_HOST}."
