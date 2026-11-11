"""
flatfox.ch: flats and shared rooms, read from Flatfox's public API. Messages are sent
on the website by the user.
"""

from collections.abc import Iterator
from typing import Any

import requests

from src.lib.flatfox_client import BASE_URL, FlatfoxClient, format_listing
from src.lib.logger import logger
from src.sites.base import Listing, SiteRunner

ZURICH_BBOX = {"west": 8.45, "east": 8.62, "south": 47.32, "north": 47.43}
DEFAULT_CATEGORIES = ("APARTMENT", "SHARED", "HOUSE")
ROOM_TYPES = ("SHARED_FLAT", "SINGLE_ROOM")


def location(record: dict[str, Any]) -> str | None:
    """
    Where a listing is, for commute lookups.

    :param record: Listing record from the API.
    :return: ``lat,lng`` if known, else the public address, else ``None``.
    """
    if record.get("latitude") and record.get("longitude"):
        return f"{record['latitude']},{record['longitude']}"
    return record.get("public_address") or None


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

    def fits(self, record: dict[str, Any]) -> bool:
        """
        Whether a listing can house the search: no single rooms for a group, and at
        least ``min_rooms`` rooms when that is set and the listing says how many.

        :param record: Listing record from the API.
        :return: ``True`` if the listing should be kept.
        """
        is_room = (
            record.get("object_category") == "SHARED"
            or record.get("object_type") in ROOM_TYPES
        )
        if self.profile.is_group and is_room:
            return False
        min_rooms = self.profile.min_rooms
        try:
            rooms = float(record.get("number_of_rooms") or 0)
        except (TypeError, ValueError):
            rooms = 0
        return not (min_rooms and rooms and rooms < min_rooms)

    def listings(self) -> Iterator[Listing]:
        """
        Yield the fetched listings that can house the search.

        :return: Iterator over listings.
        """
        kept = [record for record in self.records if self.fits(record)]
        if len(kept) < len(self.records):
            logger.info(
                "Left out %d Flatfox listings that are too small or single rooms",
                len(self.records) - len(kept),
            )
        for record in kept:
            yield Listing(
                id=str(record["pk"]),
                url=BASE_URL + record.get("url", f"/{record['pk']}/"),
                content=format_listing(record),
                location=location(record),
            )

    def close(self) -> None:
        """
        Close the HTTP session if it was opened.
        """
        client = getattr(self, "client", None)
        if client is not None:
            client.session.close()
