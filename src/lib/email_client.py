"""
Gmail helpers: send application emails and read one-time login codes.
"""

import email
import imaplib
import re
import smtplib
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage, Message
from email.utils import parsedate_to_datetime

from src.lib.logger import logger
from src.personal_profile import PersonalProfile

OTP_PATTERN = re.compile(r"\b\d{6}\b")


class EmailError(RuntimeError):
    """
    Raised when sending an email or reading a login code fails.
    """


def message_text(message: Message) -> str:
    """
    Return the plain-text body of an email, without its headers.

    :param message: Parsed email message.
    :return: Concatenated ``text/plain`` parts, decoded to a string.
    """
    parts = message.walk() if message.is_multipart() else [message]
    chunks = []
    for part in parts:
        if part.get_content_type() == "text/plain":
            payload = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            chunks.append(payload.decode(charset, errors="ignore"))
    return "\n".join(chunks)


def extract_otp(text: str) -> str | None:
    """
    Find the first 6-digit code in a piece of text.

    :param text: Text to search, typically an email body.
    :return: The code, or ``None`` if the text contains no 6-digit number.
    """
    match = OTP_PATTERN.search(text)
    return match.group(0) if match else None


class EmailClient:
    """
    Send mail through Gmail SMTP and read login codes through Gmail IMAP.
    """

    def __init__(self, profile: PersonalProfile) -> None:
        """
        Create a client for one user.

        :param profile: Profile holding the Gmail credentials.
        """
        self.profile = profile

    def gmail_send_message(self, recipient: str, subject: str, content: str) -> None:
        """
        Send an email from the user's Gmail account, with a Bcc copy to the user.

        :param recipient: Address to send to.
        :param subject: Subject line.
        :param content: Plain-text body.
        :raises EmailError: If connecting, logging in or sending fails.
        """
        email_message = EmailMessage()
        email_message.set_content(content)
        email_message["To"] = recipient
        email_message["From"] = self.profile.gmail_login
        email_message["Subject"] = subject
        email_message["Bcc"] = self.profile.gmail_login

        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(self.profile.gmail_login, self.profile.gmail_password)
                server.send_message(email_message)
        except (smtplib.SMTPException, OSError) as error:
            raise EmailError(f"Sending email to {recipient} failed: {error}") from error

    def retrieve_6digit_code(
        self,
        sender: str = "flatfox",
        max_age_minutes: int = 10,
        timeout_s: int = 60,
    ) -> str:
        """
        Poll the second inbox for a recent login code and return it.

        Only emails whose From header contains ``sender`` and that arrived within
        ``max_age_minutes`` are read. The email that held the code is deleted;
        no other email is touched.

        :param sender: Substring that must appear in the From header.
        :param max_age_minutes: Ignore emails older than this.
        :param timeout_s: How long to keep polling before giving up.
        :return: The 6-digit code.
        :raises EmailError: If no matching code arrives within ``timeout_s``.
        """
        deadline = time.monotonic() + timeout_s
        while True:
            code = self._find_code(sender, max_age_minutes)
            if code:
                return code
            if time.monotonic() >= deadline:
                raise EmailError(
                    f"No 6-digit code from '{sender}' arrived within {timeout_s}s"
                )
            time.sleep(5)

    def _find_code(self, sender: str, max_age_minutes: int) -> str | None:
        """
        Look once through the inbox for a fresh code from ``sender``.

        :param sender: Substring that must appear in the From header.
        :param max_age_minutes: Ignore emails older than this.
        :return: The code, or ``None`` if no matching email holds one yet.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        try:
            mail.login(self.profile.gmail_login2, self.profile.gmail_password2)
            mail.select("inbox")
            # IMAP SINCE only takes a date; the exact cutoff is checked per email.
            since = cutoff.strftime("%d-%b-%Y")
            _, data = mail.search(None, f'(FROM "{sender}" SINCE {since})')
            for email_id in reversed(data[0].split()):
                _, fetched = mail.fetch(email_id, "(RFC822)")
                message = email.message_from_bytes(fetched[0][1])
                if not message["Date"]:
                    continue
                sent_at = parsedate_to_datetime(message["Date"])
                if sent_at.tzinfo is None or sent_at < cutoff:
                    continue
                code = extract_otp(message_text(message))
                if code:
                    logger.info("Found login code from %s", sender)
                    mail.store(email_id, "+FLAGS", "\\Deleted")
                    mail.expunge()
                    return code
            return None
        finally:
            try:
                mail.logout()
            except (imaplib.IMAP4.error, OSError):
                pass
