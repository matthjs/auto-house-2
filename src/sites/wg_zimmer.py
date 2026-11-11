"""
wgzimmer.ch: rooms in shared flats, contacted through the site's form.
"""

from collections.abc import Iterator

from src.lib.wg_zimmer_web_interactor import WGZimmerWebInteractor
from src.sites.base import Listing, SiteRunner


class WGZimmerRunner(SiteRunner):
    """
    Walk through wgzimmer.ch results and answer through the contact form.
    """

    site = "wgzimmer.ch"

    def required_fields(self) -> tuple[str, ...]:
        """
        Profile fields this site needs in the current mode.

        :return: Search region, plus contact details unless this is a dry run.
        """
        fields = ("place_wg_zimmer",)
        if self.mode != "dry-run":
            fields += ("user_name", "user_email", "user_phone_number")
        return fields

    def start(self) -> None:
        """
        Open the browser and run the search.
        """
        self.interactor: WGZimmerWebInteractor | None = None
        self.interactor = WGZimmerWebInteractor(self.profile)
        self.interactor.load()
        self.interactor.enter()
        self.interactor.search()
        self.interactor.gather_results()

    def listings(self) -> Iterator[Listing]:
        """
        Yield results by following each listing's "next" link.

        :return: Iterator over listings.
        """
        assert self.interactor is not None
        while self.interactor.has_next_link:
            pid, text = self.interactor.visit_and_gather()
            yield Listing(id=pid, url=self.interactor.current_url or "", content=text)

    def send(self, listing: Listing, subject: str, message: str) -> None:
        """
        Submit the contact form on the current listing page.

        :param listing: The listing (its page is open).
        :param subject: Unused; the form has no subject field.
        :param message: Message body.
        :raises SendError: If the form cannot be submitted.
        """
        assert self.interactor is not None
        self.interactor.send_information(message)

    def close(self) -> None:
        """
        Close the browser if it was opened.
        """
        if getattr(self, "interactor", None) is not None:
            self.interactor.close()
