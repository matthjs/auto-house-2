"""
Saved-search alert emails from Homegate, ImmoScout24, Comparis and other portals,
read from the contact's Gmail. Messages are sent on the portals by the user.
"""

import imaplib
import re
from collections.abc import Iterator

import requests

from src.lib.alert_mail import Portal, extract_listings, fetch_alert_emails
from src.lib.logger import logger
from src.sites.base import Listing, SiteRunner


class EmailAlertsRunner(SiteRunner):
    """
    Turn recent alert emails into listings. Portals, their sender addresses and
    listing-link patterns come from ``conf/site/email_alerts.yaml``.
    Draft-only: :attr:`can_send` is ``False``.
    """

    site = "email-alerts"
    can_send = False

    def required_fields(self) -> tuple[str, ...]:
        """
        Profile fields needed to read the alerts.

        :return: The Gmail address and app password of the inbox with the alerts.
        """
        return ("gmail_login", "gmail_password")

    def portals(self) -> list[Portal]:
        """
        Build the portal list from the site options.

        :return: Portals with compiled listing patterns.
        """
        return [
            Portal(
                name=str(p["name"]),
                sender=str(p["sender"]),
                listing_pattern=re.compile(str(p["listing_pattern"])),
            )
            for p in self.options.get("portals") or []
        ]

    def start(self) -> None:
        """
        Read the alert emails and extract their listings.
        """
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "auto-house (reading alert email links)"
        self.found = []
        try:
            emails = fetch_alert_emails(
                self.profile.gmail_login,
                self.profile.gmail_password,
                self.portals(),
                days=int(self.options.get("days", 7)),
            )
        except (imaplib.IMAP4.error, OSError) as error:
            logger.error("Reading alert emails failed: %s", error)
            return
        seen: set[str] = set()
        for portal, html in emails:
            for listing in extract_listings(html, portal, self.session):
                if listing.id not in seen:
                    seen.add(listing.id)
                    self.found.append(listing)
        logger.info("Alert emails: %d emails, %d listings", len(emails), len(seen))

    def listings(self) -> Iterator[Listing]:
        """
        Yield the listings found in the emails.

        :return: Iterator over listings.
        """
        for item in self.found:
            yield Listing(id=item.id, url=item.url, content=item.text)

    def close(self) -> None:
        """
        Close the HTTP session if it was opened.
        """
        session = getattr(self, "session", None)
        if session is not None:
            session.close()
