"""
Offline tests for the listing sources: Flatfox API, WOKO, alert emails, wgzimmer.ch.
"""

import re
from types import SimpleNamespace

from src.lib.alert_mail import Portal, extract_listings, html_of
from src.lib.flatfox_client import FlatfoxClient, format_listing
from src.lib.wg_zimmer_client import WGZimmerClient
from src.lib.woko_client import parse_rooms
from src.sites.flatfox import FlatfoxRunner
from src.sites.woko import WokoRunner

FLATFOX_RECORD = {
    "pk": 101,
    "url": "/en/flat/8004-zuerich/101/",
    "object_category": "APARTMENT",
    "object_type": "APARTMENT",
    "public_title": "8004 Zürich - CHF 1900 per month",
    "number_of_rooms": "2.5",
    "rent_gross": 1900,
    "moving_date": "2027-01-01",
    "description": "Bright flat near Langstrasse.",
}


class FakeResponse:
    """
    Minimal stand-in for ``requests.Response``.
    """

    def __init__(self, payload=None, text="", status=200, headers=None) -> None:
        """
        Store what the fake server answers.

        :param payload: JSON body.
        :param text: Text body.
        :param status: HTTP status.
        :param headers: Response headers.
        """
        self.payload, self.text = payload, text
        self.status_code, self.headers = status, headers or {}

    def json(self):
        """
        Return the JSON body.

        :return: The payload.
        """
        return self.payload

    def raise_for_status(self) -> None:
        """
        Do nothing: fake responses succeed.
        """


def test_format_flatfox_listing() -> None:
    text = format_listing(FLATFOX_RECORD)
    assert "Rooms: 2.5" in text and "Rent per month (CHF): 1900" in text
    assert text.endswith("Bright flat near Langstrasse.")


def test_flatfox_search_skips_known_and_unwanted() -> None:
    client = FlatfoxClient(delay_s=0)
    calls = []

    def get(url, params, timeout):
        calls.append((url, params))
        if url.endswith("/pin/"):
            return FakeResponse([{"pk": 101}, {"pk": 102}, {"pk": 103}])
        parking = {**FLATFOX_RECORD, "pk": 103, "object_category": "PARK"}
        return FakeResponse({"results": [FLATFOX_RECORD, parking]})

    client.session = SimpleNamespace(get=get)
    found = client.search(
        bbox={"west": 1, "east": 2, "south": 3, "north": 4},
        max_price=2000,
        categories=["APARTMENT"],
        is_known=lambda pk: pk == "102",
    )
    assert [r["pk"] for r in found] == [101]
    assert ("max_price", "2000") in calls[0][1]
    assert [v for k, v in calls[1][1] if k == "pk"] == ["101", "103"]


def test_flatfox_runner_yields_listings(profile, monkeypatch) -> None:
    monkeypatch.setattr(FlatfoxClient, "search", lambda self, **kw: [FLATFOX_RECORD])
    found = FlatfoxRunner(profile).collect()
    assert found[0]["id"] == "101"
    assert found[0]["url"] == "https://flatfox.ch/en/flat/8004-zuerich/101/"


WOKO_HTML = """
<div class="crooms__element" data-price="767" data-region="Region Zürich">
  <h3 class="crooms__headline">Zimmer in 6er-WG</h3><strong>Nachmieter gesucht</strong>
  <div class="crooms__text">Wann</div><div class="crooms__text">Ab 01.12.2026</div>
  <a href="../unser-angebot/freie-objekte/detail?oid=614">Detail</a>
  <a href="../service/mietservice/bewerbung-mietobjekt?oid=1&aid=614&type=0">
   Bewerben</a>
</div>
<div class="crooms__element" data-price="1200">
  <h3 class="crooms__headline">Teures Zimmer</h3>
  <a href="../unser-angebot/freie-objekte/detail?oid=700">Detail</a>
  <a href="../service/mietservice/bewerbung-mietobjekt?oid=2&aid=700&type=0">
   Bewerben</a>
</div>
<div class="crooms__element" data-price="90">
  <h3 class="crooms__headline">Parkplatz</h3>
  <a href="../unser-angebot/freie-objekte/detail?oid=5">Detail</a>
  <a href="../service/mietservice/bewerbung-mietobjekt?oid=3&aid=5&type=1">Bewerben</a>
</div>
"""


def test_woko_parser_drops_parking() -> None:
    rooms = parse_rooms(WOKO_HTML, "https://www.woko.ch/unser-angebot/freie-objekte")
    assert [r["id"] for r in rooms] == ["614", "700"]
    assert rooms[0]["price"] == 767
    assert rooms[0]["url"].endswith("/unser-angebot/freie-objekte/detail?oid=614")
    assert "Wann: Ab 01.12.2026" in rooms[0]["text"]


def test_woko_runner_keeps_rooms_within_budget(profile, monkeypatch) -> None:
    monkeypatch.setattr(
        "src.sites.woko.fetch_rooms", lambda: parse_rooms(WOKO_HTML, "https://w.ch/")
    )
    found = WokoRunner(profile).collect()
    assert [item["id"] for item in found] == ["614"]
    assert "Bewerben (apply)" in found[0]["text"]


HOMEGATE = Portal(
    name="homegate",
    sender="homegate.ch",
    listing_pattern=re.compile(r"homegate\.ch/(?:[a-z]{2}/)?(?:rent|mieten)/(\d{6,})"),
)
ALERT_HTML = """
<table>
 <tr><td><a href="https://www.homegate.ch/rent/4001234567?utm=alert">
   <img src="x.jpg"></a>
   <p>3.5 Zimmer, 8004 Zürich, CHF 2'350 pro Monat, frei ab 1.2.2027</p>
   <a href="https://www.homegate.ch/rent/4001234567?utm=alert2">Ansehen</a></td></tr>
 <tr><td><a href="https://click.example.com/abc">
   2 Zimmer in Wiedikon, CHF 1'800 / Monat</a></td></tr>
 <tr><td><a href="https://www.homegate.ch/unsubscribe">Abmelden</a></td></tr>
</table>
"""


def test_alert_email_listings_and_tracking_redirects() -> None:
    def head(url, allow_redirects, timeout):
        assert allow_redirects is False
        if url == "https://click.example.com/abc":
            return FakeResponse(
                status=302,
                headers={"Location": "https://www.homegate.ch/mieten/4009999999"},
            )
        return FakeResponse(status=200)

    session = SimpleNamespace(head=head)
    found = extract_listings(ALERT_HTML, HOMEGATE, session)
    assert [item.id for item in found] == ["homegate-4001234567", "homegate-4009999999"]
    assert found[0].url == "https://www.homegate.ch/rent/4001234567"
    assert "CHF 2'350" in found[0].text
    assert "Wiedikon" in found[1].text


def test_plain_text_alert_email_becomes_links() -> None:
    import email

    raw = (
        b"Content-Type: text/plain\r\n\r\nNeu: https://www.homegate.ch/rent/4001234567"
    )
    assert 'href="https://www.homegate.ch/rent/4001234567"' in html_of(
        email.message_from_bytes(raw)
    )


def test_wgzimmer_search_stops_at_a_page_with_nothing_new() -> None:
    client = WGZimmerClient(delay_s=0)
    pages = []

    def get(url, params=None):
        pages.append(params.get("seite", "1"))
        n = int(params.get("seite", "1"))
        link = (
            '<a class="result-row__link" href="/wg-zimmer/zuerich/8004-z-{}.html">x</a>'
        )
        return link.format(f"{n}a") + link.format(f"{n}b")

    client._get = get
    urls = client.search("zuerich", 900, max_pages=5, is_known=lambda _id: True)
    assert pages == ["1"] and len(urls) == 2
    pages.clear()
    client.search("zuerich", 900, max_pages=3, is_known=lambda _id: False)
    assert pages == ["1", "2", "3"]
