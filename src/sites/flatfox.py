"""
flatfox.ch: flats and shared rooms, read from Flatfox's public API. Messages are sent
on the website by the user.
"""

from collections.abc import Iterator

import requests

from src.lib.flatfox_client import BASE_URL, FlatfoxClient, format_listing
from src.lib.logger import logger
from src.sites.base import Listing, SiteRunner

ZURICH_BBOX = {"west": 8.45, "east": 8.62, "south": 47.32, "north": 47.43}
DEFAULT_CATEGORIES = ("APARTMENT", "SHARED", "HOUSE")


class FlatfoxRunner(SiteRunner):
    """
    Search Flatfox by map area (``site.bbox``) and the search's budget. No login.
    Draft-only: :attr:`can_send` is ``False``.
    """

    site = "flatfox.ch"
    can_send = False

    def required_fields(self) -> tuple[str, ...]:
        """
        Profile fields needed to search.

        :return: None; the area comes from ``conf/site/flatfox.yaml``.
        """
        return ()

    def start(self) -> None:
        """
        Fetch the pins for the area and the details of new listings.
        """
        self.client = FlatfoxClient()
        bbox = self.options.get("bbox") or ZURICH_BBOX
        try:
            self.records = self.client.search(
                bbox=dict(bbox),
                max_price=self.profile.max_rent,
                categories=self.options.get("categories") or DEFAULT_CATEGORIES,
                is_known=self.tracker.is_done,
                max_count=int(self.options.get("max_count", 400)),
            )
        except requests.RequestException as error:
            logger.error("Flatfox search failed: %s", error)
            self.records = []

    def listings(self) -> Iterator[Listing]:
        """
        Yield the fetched listings.

        :return: Iterator over listings.
        """
        for record in self.records:
            yield Listing(
                id=str(record["pk"]),
                url=BASE_URL + record.get("url", f"/{record['pk']}/"),
                content=format_listing(record),
            )

    def close(self) -> None:
        """
        Close the HTTP session if it was opened.
        """
        client = getattr(self, "client", None)
        if client is not None:
            client.session.close()
