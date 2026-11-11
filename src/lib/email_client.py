"""
Gmail helper: send application emails and the digest.
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
        self._send([recipient], subject, content, bcc_self=True)

    def send_digest(self, recipients: list[str], subject: str, content: str) -> None:
        """
        Send the digest to the search's own members.

        :param recipients: Members' addresses.
        :param subject: Subject line.
        :param content: Plain-text body.
        :raises EmailError: If there is no recipient, or sending fails.
        """
        if not recipients:
            raise EmailError("No member has an Email in their person file")
        self._send(recipients, subject, content, bcc_self=False)

    def _send(
        self, recipients: list[str], subject: str, content: str, bcc_self: bool
    ) -> None:
        """
        Send one plain-text email through Gmail SMTP.

        :param recipients: Addresses to send to.
        :param subject: Subject line.
        :param content: Plain-text body.
        :param bcc_self: Also send a Bcc copy to the sender.
        :raises EmailError: If connecting, logging in or sending fails.
        """
        email_message = EmailMessage()
        email_message.set_content(content)
        email_message["To"] = ", ".join(recipients)
        email_message["From"] = self.profile.gmail_login
        email_message["Subject"] = subject
        if bcc_self:
            email_message["Bcc"] = self.profile.gmail_login

        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(self.profile.gmail_login, self.profile.gmail_password)
                server.send_message(email_message)
        except (smtplib.SMTPException, OSError) as error:
            raise EmailError(
                f"Sending email to {', '.join(recipients)} failed: {error}"
            ) from error
