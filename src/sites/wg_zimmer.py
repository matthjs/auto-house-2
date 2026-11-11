"""
wgzimmer.ch: rooms in shared flats. Read over plain HTTP; messages are sent by hand
because the contact form has a bot check.
"""

from collections.abc import Iterator

import requests

from src.lib.logger import logger
from src.lib.wg_zimmer_client import WGZimmerClient, listing_id
from src.sites.base import Listing, SiteRunner


class WGZimmerRunner(SiteRunner):
    """
    Search wgzimmer.ch by region and maximum rent. Draft-only: :attr:`can_send` is
    ``False``, so the user pastes approved messages into the site.
    """

    site = "wgzimmer.ch"
    can_send = False

    def required_fields(self) -> tuple[str, ...]:
        """
        Profile fields needed to search.

        :return: The wgzimmer.ch region.
        """
        return ("place_wg_zimmer",)

    def start(self) -> None:
        """
        Fetch the result pages and remember the listing URLs.
        """
        self.client = WGZimmerClient()
        self.urls = self.client.search(
            region=self.profile.place_wg_zimmer,
            max_rent=self.profile.max_rent,
            max_pages=int(self.options.get("max_pages", 3)),
            is_known=lambda pid: self.tracker.get(pid) is not None,
        )

    def listings(self) -> Iterator[Listing]:
        """
        Fetch each listing that is not handled yet. Listings seen before reuse their
        saved text instead of being fetched again; failures are logged and skipped.

        :return: Iterator over listings.
        """
        for url in self.urls:
            pid = listing_id(url.removeprefix("https://www.wgzimmer.ch"))
            record = self.tracker.get(pid)
            if record is not None and (self.tracker.is_done(pid) or record.get("text")):
                yield Listing(id=pid, url=url, content=record.get("text", ""))
                continue
            try:
                text = self.client.listing(url)
            except (requests.RequestException, ValueError) as error:
                logger.warning("Could not read %s: %s", url, error)
                continue
            yield Listing(id=pid, url=url, content=text)

    def close(self) -> None:
        """
        Close the HTTP session if it was opened.
        """
        client = getattr(self, "client", None)
        if client is not None:
            client.session.close()
