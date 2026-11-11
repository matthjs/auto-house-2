"""
Gmail helper: send application emails.
"""

import re
import smtplib
from email.message import EmailMessage

from src.search_profile import SearchProfile

OTP_PATTERN = re.compile(r"\b\d{6}\b")


class EmailError(RuntimeError):
    """
    Raised when sending an email fails.
    """


class EmailClient:
    """
    Send mail through Gmail SMTP.
    """

    def __init__(self, profile: SearchProfile) -> None:
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
