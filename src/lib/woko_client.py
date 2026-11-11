"""
Client for WOKO's list of free student rooms in Zurich (one public page).

Applying happens through WOKO's own form, so this source is draft-only.
"""

import re
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

FREE_ROOMS_URL = "https://www.woko.ch/unser-angebot/freie-objekte"
USER_AGENT = "Mozilla/5.0 (compatible; auto-house; personal housing search)"


def parse_rooms(html: str, base_url: str = FREE_ROOMS_URL) -> list[dict[str, Any]]:
    """
    Read the free rooms from WOKO's list page, leaving out parking spaces.

    :param html: The list page HTML.
    :param base_url: URL the page was loaded from, to make links absolute.
    :return: One dict per room: ``id``, ``url``, ``apply_url``, ``price``,
        ``address`` (``None`` if not shown) and ``text``.
    """
    soup = BeautifulSoup(html, "html.parser")
    rooms = []
    for element in soup.select(".crooms__element"):
        apply_link = element.find("a", href=re.compile(r"bewerbung-mietobjekt"))
        detail_link = element.find("a", href=re.compile(r"freie-objekte/detail"))
        if apply_link is None or detail_link is None:
            continue
        apply_query = parse_qs(urlparse(apply_link["href"]).query)
        if apply_query.get("type", ["0"])[0] != "0":
            continue  # type=1 is parking
        room_id = parse_qs(urlparse(detail_link["href"]).query).get("oid", [""])[0]
        if not room_id:
            continue

        lines = []
        headline = element.select_one(".crooms__headline")
        if headline:
            lines.append(headline.get_text(" ", strip=True))
        status = element.find("strong")
        if status:
            lines.append(status.get_text(" ", strip=True))
        texts = [t.get_text(" ", strip=True) for t in element.select(".crooms__text")]
        facts = dict(zip(texts[0::2], texts[1::2], strict=False))
        for key, value in facts.items():
            lines.append(f"{key}: {value}")
        street, town = facts.get("Adresse"), facts.get("Ort")
        address = f"{street}, {town}" if street and town else None
        price_text = element.get("data-price") or ""
        if price_text:
            lines.append(f"Miete/Monat: CHF {price_text}")
        region = element.get("data-region")
        if region:
            lines.append(f"Region: {region}")

        rooms.append(
            {
                "id": room_id,
                "url": urljoin(base_url, detail_link["href"]),
                "apply_url": urljoin(base_url, apply_link["href"]),
                "price": int(price_text) if price_text.isdigit() else None,
                "address": address,
                "text": "\n".join(lines),
            }
        )
    return rooms


def fetch_rooms() -> list[dict[str, Any]]:
    """
    Download and parse WOKO's free rooms (one request).

    :return: Rooms as returned by :func:`parse_rooms`.
    :raises requests.HTTPError: If the server answers with an error status.
    """
    response = requests.get(
        FREE_ROOMS_URL, headers={"User-Agent": USER_AGENT}, timeout=30
    )
    response.raise_for_status()
    return parse_rooms(response.text, response.url)
