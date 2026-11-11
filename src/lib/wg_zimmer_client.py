"""
Plain-HTTP client for wgzimmer.ch search results and listing pages.

The pages are public and server-rendered, so no browser is needed. Contacting a
landlord is behind a bot check (Cloudflare Turnstile) and is left to the user.
"""

import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.wgzimmer.ch"
SEARCH_PATH = "/wgzimmer/search/mate.html"
LISTING_PATTERN = re.compile(r"^/wg-zimmer/[^/]+/([a-z0-9\-]+)\.html$")
USER_AGENT = "Mozilla/5.0 (compatible; auto-house; personal housing search)"
REQUEST_DELAY_S = 1.5
NOISE_SELECTORS = "script, style, template, noscript, svg, .ad-slot"


def listing_id(path: str) -> str:
    """
    Extract the listing id from a listing link.

    :param path: Link path, for example
        ``/wg-zimmer/zuerich/8004-zuerich-9fba8857.html``.
    :return: The id, for example ``8004-zuerich-9fba8857``.
    :raises ValueError: If the path is not a listing link.
    """
    match = LISTING_PATTERN.match(path)
    if not match:
        raise ValueError(f"Not a listing link: {path}")
    return match.group(1)


def parse_results(html: str) -> list[str]:
    """
    Collect the listing links on one results page.

    :param html: Results page HTML.
    :return: Listing paths in page order, without duplicates.
    """
    soup = BeautifulSoup(html, "html.parser")
    paths: list[str] = []
    for link in soup.select("a.result-row__link[href]"):
        path = link["href"]
        if LISTING_PATTERN.match(path) and path not in paths:
            paths.append(path)
    return paths


def parse_listing(html: str) -> str:
    """
    Turn a listing page into plain text: title, rent, facts and description.

    :param html: Listing page HTML.
    :return: The listing as text, one item per line.
    :raises ValueError: If the page has no listing content.
    """
    soup = BeautifulSoup(html, "html.parser")
    for noise in soup.select(NOISE_SELECTORS):
        noise.decompose()

    lines: list[str] = []
    title = soup.select_one(".page__title-text")
    if title:
        lines.append(title.get_text(" ", strip=True))
    rent = soup.select_one(".ad-page__rent")
    if rent:
        lines.append(rent.get_text(" ", strip=True))
    facts = soup.select_one(".ad-page__facts")
    if facts:
        for term in facts.find_all("dt"):
            value = term.find_next_sibling("dd")
            if value:
                label = term.get_text(" ", strip=True)
                lines.append(f"{label}: {value.get_text(' ', strip=True)}")
    for text in soup.select(".ad-page__text"):
        content = text.get_text("\n", strip=True)
        if content:
            lines.append(content)

    if not lines:
        raise ValueError("No listing content found on the page")
    return "\n".join(lines)


class WGZimmerClient:
    """
    Fetch wgzimmer.ch search results and listings politely (one request at a time,
    with a pause between requests).
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

    def _get(self, url: str, params: dict[str, str] | None = None) -> str:
        """
        Fetch a page.

        :param url: Absolute URL.
        :param params: Query parameters.
        :return: The response body.
        :raises requests.HTTPError: If the server answers with an error status.
        """
        if self._requested:
            time.sleep(self.delay_s)
        self._requested = True
        response = self.session.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.text

    def search(self, region: str, max_rent: int, max_pages: int) -> list[str]:
        """
        Collect listing URLs for a region and maximum rent.

        :param region: Region value from the search form, for example ``zuerich``.
        :param max_rent: Maximum rent in CHF.
        :param max_pages: Most result pages to read (24 listings per page).
        :return: Absolute listing URLs, newest first as the site sorts them.
        """
        urls: list[str] = []
        for page in range(1, max_pages + 1):
            params = {"region": region, "max": str(max_rent)}
            if page > 1:
                params["seite"] = str(page)
            paths = parse_results(self._get(BASE_URL + SEARCH_PATH, params))
            new = [
                urljoin(BASE_URL, p) for p in paths if urljoin(BASE_URL, p) not in urls
            ]
            if not new:
                break
            urls.extend(new)
        return urls

    def listing(self, url: str) -> str:
        """
        Fetch one listing as text.

        :param url: Absolute listing URL.
        :return: The listing text.
        """
        return parse_listing(self._get(url))
