"""Sending the verification email. Standard library only.

  SmtpMailer     sends through any SMTP account (Gmail with an app password, Brevo, Resend, SendGrid, Mailgun...).
  ConsoleMailer  prints the message in the server's terminal instead. For trying things locally only: nobody
                 receives anything, so a site that people sign up to must configure SMTP.

Both have one method, `send(to, subject, body)`, which raises MailError if the message could not be sent.
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage

log = logging.getLogger(__name__)


class MailError(Exception):
    """The message could not be sent (server unreachable, login refused, address rejected)."""


class ConsoleMailer:
    def send(self, to: str, subject: str, body: str) -> None:
        bar = "-" * 70
        print(f"\n{bar}\nEMAIL (printed here, not sent: SMTP_HOST is not set)\nTo: {to}\nSubject: {subject}\n\n{body}\n{bar}\n", flush=True)


class SmtpMailer:
    def __init__(self, host: str, port: int = 587, user: str = "", password: str = "", sender: str = "",
                 security: str = "starttls", timeout: float = 10.0):
        if security not in ("starttls", "ssl", "none"):
            raise ValueError("SMTP_SECURITY must be starttls, ssl or none")
        self.host, self.port, self.user, self.password = host, port, user, password
        self.sender = sender or user
        self.security, self.timeout = security, timeout
        if not self.sender:
            raise ValueError("Set SMTP_FROM (or SMTP_USER) so the email has a sender address")

    def send(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = self.sender, to, subject
        message.set_content(body)
        try:
            if self.security == "ssl":
                client = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=ssl.create_default_context())
            else:
                client = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
            with client:
                if self.security == "starttls":
                    client.starttls(context=ssl.create_default_context())
                if self.user:
                    client.login(self.user, self.password)
                client.send_message(message)
        except (smtplib.SMTPException, OSError) as error:
            log.error("could not send email to %s: %s", to, error)
            raise MailError(str(error)) from error


def mailer_from_env(env) -> ConsoleMailer | SmtpMailer:
    """SmtpMailer when SMTP_HOST is set, otherwise the console one."""
    host = env.get("SMTP_HOST", "").strip()
    if not host:
        return ConsoleMailer()
    return SmtpMailer(
        host, port=int(env.get("SMTP_PORT", "587")), user=env.get("SMTP_USER", ""), password=env.get("SMTP_PASSWORD", ""),
        sender=env.get("SMTP_FROM", ""), security=env.get("SMTP_SECURITY", "starttls").lower(),
    )
