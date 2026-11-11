"""
Client for Flatfox's public JSON API: map pins for an area, then listing details.

No login and no browser are needed. Contacting a landlord happens on the website.
"""

import time
from collections.abc import Callable, Iterable
from typing import Any

import requests

BASE_URL = "https://flatfox.ch"
PIN_PATH = "/api/v1/pin/"
LISTING_PATH = "/api/v1/public-listing/"
USER_AGENT = "Mozilla/5.0 (compatible; auto-house; personal housing search)"
REQUEST_DELAY_S = 1.0
BATCH_SIZE = 50


def format_listing(data: dict[str, Any]) -> str:
    """
    Turn one public-listing record into plain text for judging and drafting.

    :param data: One item of the ``public-listing`` API's ``results``.
    :return: The listing as text, one fact per line, then the description.
    """
    rent = data.get("rent_gross") or data.get("price_display")
    facts = [
        ("Title", data.get("public_title") or data.get("short_title")),
        ("Type", f"{data.get('object_category')} / {data.get('object_type')}"),
        ("Rooms", data.get("number_of_rooms")),
        ("Living space (m²)", data.get("surface_living")),
        ("Rent per month (CHF)", rent),
        ("Net rent (CHF)", data.get("rent_net")),
        ("Charges (CHF)", data.get("rent_charges")),
        ("Address", data.get("public_address")),
        ("Available from", data.get("moving_date") or data.get("moving_date_type")),
        ("Furnished", data.get("is_furnished")),
        ("Temporary", data.get("is_temporary")),
    ]
    lines = [f"{label}: {value}" for label, value in facts if value not in (None, "")]
    if data.get("description_title"):
        lines.append(str(data["description_title"]))
    if data.get("description"):
        lines.append(str(data["description"]).strip())
    return "\n".join(lines)


class FlatfoxClient:
    """
    Fetch Flatfox listings for a map area and budget, politely (one request at a
    time, with a pause between requests).
    """

    def __init__(self, delay_s: float = REQUEST_DELAY_S) -> None:
        """
        Create an HTTP session.

        :param delay_s: Seconds to wait before each request after the first.
        """
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.delay_s = delay_s
        self._requested = False

    def _get(self, path: str, params: list[tuple[str, str]]) -> Any:
        """
        Fetch one API response.

        :param path: API path.
        :param params: Query parameters (a list, so keys can repeat).
        :return: The decoded JSON.
        :raises requests.HTTPError: If the server answers with an error status.
        """
        if self._requested:
            time.sleep(self.delay_s)
        self._requested = True
        response = self.session.get(BASE_URL + path, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def pins(
        self, bbox: dict[str, float], max_price: int, max_count: int = 400
    ) -> list[int]:
        """
        Find the ids of listings in a map area up to a price.

        :param bbox: ``west``, ``east``, ``south`` and ``north`` in degrees.
        :param max_price: Highest monthly price in CHF.
        :param max_count: Most pins to return.
        :return: Listing ids.
        """
        params = [(key, str(bbox[key])) for key in ("west", "east", "south", "north")]
        params += [("max_price", str(max_price)), ("max_count", str(max_count))]
        return [pin["pk"] for pin in self._get(PIN_PATH, params)]

    def listings(self, pks: Iterable[int]) -> list[dict[str, Any]]:
        """
        Fetch the details of listings by id, in batches.

        :param pks: Listing ids.
        :return: Listing records from the API.
        """
        pks = list(pks)
        records: list[dict[str, Any]] = []
        for start in range(0, len(pks), BATCH_SIZE):
            batch = pks[start : start + BATCH_SIZE]
            params = [("limit", str(len(batch)))] + [("pk", str(pk)) for pk in batch]
            records.extend(self._get(LISTING_PATH, params)["results"])
        return records

    def search(
        self,
        bbox: dict[str, float],
        max_price: int,
        categories: Iterable[str],
        is_known: Callable[[str], bool] = lambda _id: False,
        max_count: int = 400,
    ) -> list[dict[str, Any]]:
        """
        Fetch details of the listings in an area that are not known yet.

        :param bbox: Map area (see :meth:`pins`).
        :param max_price: Highest monthly price in CHF.
        :param categories: Flatfox object categories to keep, e.g. ``APARTMENT``.
        :param is_known: Returns ``True`` for listing ids that need no fetching.
        :param max_count: Most pins to consider.
        :return: Listing records of the wanted categories.
        """
        wanted = set(categories)
        pins = self.pins(bbox, max_price, max_count)
        new = [pk for pk in pins if not is_known(str(pk))]
        return [r for r in self.listings(new) if r.get("object_category") in wanted]
