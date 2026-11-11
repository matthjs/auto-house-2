"""
woko.ch: student rooms in Zurich from WOKO's public list. Applying happens through
WOKO's form, by the user.
"""

from collections.abc import Iterator

import requests

from src.lib.logger import logger
from src.lib.woko_client import fetch_rooms
from src.sites.base import Listing, SiteRunner


class WokoRunner(SiteRunner):
    """
    Read WOKO's free rooms (one request) and keep those within budget.
    Draft-only: :attr:`can_send` is ``False``. Only students can rent from WOKO.
    """

    site = "woko.ch"
    can_send = False

    def required_fields(self) -> tuple[str, ...]:
        """
        Profile fields needed to search.

        :return: None.
        """
        return ()

    def start(self) -> None:
        """
        Download the list of free rooms.
        """
        try:
            self.rooms = fetch_rooms()
        except requests.RequestException as error:
            logger.error("WOKO search failed: %s", error)
            self.rooms = []

    def listings(self) -> Iterator[Listing]:
        """
        Yield rooms within the search's budget.

        :return: Iterator over listings.
        """
        for room in self.rooms:
            if room["price"] is not None and room["price"] > self.profile.max_rent:
                continue
            text = f"{room['text']}\nBewerben (apply): {room['apply_url']}"
            yield Listing(
                id=room["id"],
                url=room["url"],
                content=text,
                location=room.get("address"),
            )

    def close(self) -> None:
        """
        Nothing to close.
        """
