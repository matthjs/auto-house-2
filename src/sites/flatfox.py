"""
flatfox.ch: flats and shared rooms, contacted through the site's form.
"""

from collections.abc import Iterator

from selenium.common.exceptions import WebDriverException

from src.lib.email_client import EmailClient
from src.lib.flatfox_web_interactor import FlatfoxWebInteractor
from src.lib.logger import logger
from src.sites.base import Listing, SiteRunner


class FlatfoxRunner(SiteRunner):
    """
    Search flatfox.ch and answer through the contact form.

    Logging in needs a one-time code that Flatfox emails to the account; it is read
    from the second Gmail inbox (``login2``/``password2``).
    """

    site = "flatfox.ch"

    def required_fields(self) -> tuple[str, ...]:
        """
        Profile fields this site needs in the current mode.

        :return: Login, code inbox and place, plus contact details unless dry run.
        """
        fields = (
            "flatfox_login",
            "flatfox_password",
            "gmail_login2",
            "gmail_password2",
            "place",
        )
        if self.mode != "dry-run":
            fields += ("user_name", "user_phone_number")
        return fields

    def start(self) -> None:
        """
        Open the browser, log in and run the search.
        """
        self.interactor: FlatfoxWebInteractor | None = None
        self.interactor = FlatfoxWebInteractor(self.profile, EmailClient(self.profile))
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
                listing_id, html = self.interactor.visit_and_gather(url)
            except (ValueError, WebDriverException) as error:
                logger.warning("Could not read %s: %s", url, error)
                continue
            yield Listing(id=listing_id, url=url, content=html)

    def send(self, listing: Listing, subject: str, message: str) -> None:
        """
        Post the contact form of the current listing.

        :param listing: The listing (its page is open).
        :param subject: Unused; the form has no subject field.
        :param message: Message body.
        :raises SendError: If Flatfox does not accept the message.
        """
        assert self.interactor is not None
        self.interactor.send_information(message)

    def close(self) -> None:
        """
        Close the browser if it was opened.
        """
        if getattr(self, "interactor", None) is not None:
            self.interactor.close()
