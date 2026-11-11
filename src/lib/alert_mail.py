"""
Read saved-search alert emails (Homegate, ImmoScout24, Comparis, ...) from Gmail and
turn them into listings.

The portals' own alerts are the sanctioned way to follow them: their sites block
scrapers, so this never loads a portal page. Each listing's text comes from the
email itself; the link is for the user to open.
"""

import email
import imaplib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import Message

import requests
from bs4 import BeautifulSoup, Tag

USER_AGENT = "Mozilla/5.0 (compatible; auto-house; personal housing search)"
MAX_REDIRECTS = 3
MIN_BLOCK_CHARS = 40
MAX_BLOCK_CHARS = 1500


@dataclass
class Portal:
    """
    How to recognise one portal's alert emails and listing links.
    """

    name: str
    sender: str
    listing_pattern: re.Pattern[str]


@dataclass
class AlertListing:
    """
    One listing found in an alert email.
    """

    id: str
    url: str
    text: str


def html_of(message: Message) -> str:
    """
    Return an email's HTML body, or its plain text wrapped as HTML.

    :param message: Parsed email.
    :return: HTML string (may be empty).
    """
    parts = message.walk() if message.is_multipart() else [message]
    html, text = "", ""
    for part in parts:
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        decoded = payload.decode(part.get_content_charset() or "utf-8", "ignore")
        if part.get_content_type() == "text/html" and not html:
            html = decoded
        elif part.get_content_type() == "text/plain" and not text:
            text = decoded
    if html:
        return html
    links = re.sub(r"(https?://\S+)", r'<a href="\1">\1</a>', text)
    return "<p>" + links.replace("\n\n", "</p><p>") + "</p>"


def resolve(url: str, portal: Portal, session: requests.Session) -> str | None:
    """
    Turn a link from an email into a portal listing URL.

    Tracking links are followed by reading ``Location`` headers only; the final
    listing page is never downloaded.

    :param url: Link from the email.
    :param portal: Portal whose listing links to accept.
    :param session: HTTP session for following redirects.
    :return: The listing URL, or ``None`` if the link is not a listing.
    """
    for _ in range(MAX_REDIRECTS + 1):
        if portal.listing_pattern.search(url):
            return url
        if not url.startswith("http"):
            return None
        try:
            response = session.head(url, allow_redirects=False, timeout=15)
        except requests.RequestException:
            return None
        location = response.headers.get("Location")
        if not location or response.status_code not in (301, 302, 303, 307, 308):
            return None
        url = requests.compat.urljoin(url, location)
    return None


def block_text(link: Tag) -> str:
    """
    Text of the smallest element around a link that says something about it.

    :param link: The ``<a>`` element.
    :return: Up to :data:`MAX_BLOCK_CHARS` characters of text.
    """
    node: Tag | None = link
    text = link.get_text(" ", strip=True)
    for _ in range(6):
        if node is None or len(text) >= MIN_BLOCK_CHARS:
            break
        node = node.parent
        if node is not None:
            text = node.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)[:MAX_BLOCK_CHARS]


def extract_listings(
    html: str, portal: Portal, session: requests.Session
) -> list[AlertListing]:
    """
    Find the listings in one alert email.

    :param html: The email's HTML.
    :param portal: Portal the email came from.
    :param session: HTTP session for following tracking links.
    :return: Listings in email order, one per listing id.
    """
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, AlertListing] = {}
    seen_links: set[str] = set()
    for link in soup.find_all("a", href=True):
        href = link["href"].strip()
        if href in seen_links:
            continue
        seen_links.add(href)
        url = resolve(href, portal, session)
        match = portal.listing_pattern.search(url or "")
        if not url or not match:
            continue
        listing_id = f"{portal.name}-{match.group(1)}"
        text = block_text(link)
        current = found.get(listing_id)
        if current is None or len(text) > len(current.text):
            clean_url = url.split("?")[0]
            found[listing_id] = AlertListing(id=listing_id, url=clean_url, text=text)
    return list(found.values())


def fetch_alert_emails(
    address: str, password: str, portals: list[Portal], days: int
) -> list[tuple[Portal, str]]:
    """
    Download recent alert emails from Gmail over IMAP (read-only).

    :param address: Gmail address that receives the alerts.
    :param password: Gmail app password.
    :param portals: Portals to look for, by sender.
    :param days: How many days back to read.
    :return: ``(portal, html)`` per email, oldest first.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d-%b-%Y")
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    emails: list[tuple[Portal, str]] = []
    try:
        mail.login(address, password)
        mail.select("inbox", readonly=True)
        for portal in portals:
            _, data = mail.search(None, f'(FROM "{portal.sender}" SINCE {since})')
            for email_id in data[0].split():
                _, fetched = mail.fetch(email_id, "(BODY.PEEK[])")
                message = email.message_from_bytes(fetched[0][1])
                emails.append((portal, html_of(message)))
    finally:
        try:
            mail.logout()
        except (imaplib.IMAP4.error, OSError):
            pass
    return emails
