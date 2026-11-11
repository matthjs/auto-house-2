"""
wohnen.ethz.ch: the ETH/UZH housing office; landlords are contacted by email.
"""

from collections.abc import Iterator

from selenium.common.exceptions import WebDriverException

from src.lib.email_client import EmailClient
from src.lib.logger import logger
from src.lib.wohnen_ethz_web_interactor import WohnenETHZWebInteractor
from src.sites.base import Listing, SiteRunner


class WohnenETHZRunner(SiteRunner):
    """
    Search wohnen.ethz.ch and email the landlord of each listing from Gmail.
    """

    site = "wohnen.ethz.ch"
    needs_contact_email = True

    def required_fields(self) -> tuple[str, ...]:
        """
        Profile fields needed to search.

        :return: wohnen.ethz.ch login and the place.
        """
        return ("wohnen_ethz_login", "wohnen_ethz_password", "place")

    def send_fields(self) -> tuple[str, ...]:
        """
        Profile fields needed to send a message.

        :return: The fields used when contacting a landlord.
        """
        return ("gmail_login", "gmail_password")

    def start(self) -> None:
        """
        Open the browser, log in and run the search.
        """
        self.interactor: WohnenETHZWebInteractor | None = None
        self.interactor = WohnenETHZWebInteractor(self.profile)
        self.interactor.load()
        self.interactor.enter()
        self.interactor.search()
        self.urls = self.interactor.gather_results()

    def listings(self) -> Iterator[Listing]:
        """
        Visit each result; listings that fail to load are logged and skipped.

        :return: Iterator over listings.
        """
        assert self.interactor is not None
        for url in self.urls:
            try:
                pid, email, html = self.interactor.visit_and_gather(url)
            except (ValueError, WebDriverException) as error:
                logger.warning("Could not read %s: %s", url, error)
                continue
            yield Listing(id=pid, url=url, content=html, contact_email=email)

    def send(self, listing: Listing, subject: str, message: str) -> None:
        """
        Email the landlord.

        :param listing: The listing, with ``contact_email`` set.
        :param subject: Email subject.
        :param message: Email body.
        :raises EmailError: If sending fails.
        """
        assert listing.contact_email
        EmailClient(self.profile).gmail_send_message(
            listing.contact_email, subject, message
        )

    def close(self) -> None:
        """
        Close the browser if it was opened.
        """
        if getattr(self, "interactor", None) is not None:
            self.interactor.close()
