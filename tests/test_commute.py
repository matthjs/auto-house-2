"""
Offline tests for commute times, the places in a search and Flatfox's group filter.
"""

from datetime import date
from types import SimpleNamespace

import pytest
import requests

from src.lib.commute import CommuteClient, Place, next_weekday, parse_duration
from src.lib.woko_client import parse_rooms
from src.search_profile import Person, ProfileError, SearchProfile
from src.sites.base import Listing
from src.sites.flatfox import FlatfoxRunner
from tests.conftest import FakeSite

ETH = Place(name="ETH Zentrum", address="Rämistrasse 101, 8092 Zürich", who=["ben"])


class FakeCommute:
    """
    Commute client that answers from a table and counts lookups.
    """

    def __init__(self) -> None:
        """
        Start with no lookups.
        """
        self.lookups = 0
        self.closed = False

    def describe(self, origin: str, places: list[Place], names: dict[str, str]) -> str:
        """
        Pretend every place is 20 minutes away.

        :param origin: Listing location.
        :param places: Places.
        :param names: Display names.
        :return: A commute section.
        """
        self.lookups += 1
        who = names[places[0].who[0]]
        return f"Commute by public transport:\n- {places[0].name}: 20 min ({who})"

    def close(self) -> None:
        """
        Remember that close was called.
        """
        self.closed = True


def group(tmp_path, places=(ETH,), min_rooms=3) -> SearchProfile:
    """
    Build a two-person search.

    :param tmp_path: Pytest's temporary directory.
    :param places: Places of the search.
    :param min_rooms: Fewest rooms.
    :return: The search.
    """
    return SearchProfile(
        "anna_ben",
        members=[Person("anna", {"Name": "Anna"}), Person("ben", {"Name": "Ben"})],
        contact="anna",
        preferences={"budget_total": 3000, "min_rooms": min_rooms},
        data_root=tmp_path / "data",
        places=places,
    )


def test_parse_duration_and_weekday() -> None:
    assert parse_duration("00d00:26:00") == 26
    assert parse_duration("01d01:02:00") == 24 * 60 + 62
    with pytest.raises(ValueError):
        parse_duration("26 min")
    assert next_weekday(date(2026, 11, 11)) == date(2026, 11, 17)  # Wed -> Tue
    assert next_weekday(date(2026, 11, 17)) == date(2026, 11, 24)  # Tue -> next Tue


def test_commute_client_takes_fastest_and_survives_errors() -> None:
    client = CommuteClient(delay_s=0, day=date(2026, 11, 17))
    seen = []

    def get(url, params, timeout):
        seen.append(params)
        if params["to"] == "nowhere":
            raise requests.ConnectionError("down")
        durations = ["00d00:31:00", "00d00:24:00", "00d00:28:00"]
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"connections": [{"duration": d} for d in durations]},
        )

    client.session = SimpleNamespace(get=get, close=lambda: None)
    assert client.minutes("47.37,8.50", "Rämistrasse 101, 8092 Zürich") == 24
    assert seen[0]["date"] == "2026-11-17" and seen[0]["time"] == "08:00"
    assert client.minutes("47.37,8.50", "nowhere") is None
    text = client.describe("47.37,8.50", [ETH], {"ben": "Ben"})
    assert "- ETH Zentrum: 24 min (Ben)" in text


def test_runner_adds_commute_once_and_keeps_it(tmp_path) -> None:
    commute = FakeCommute()

    def site() -> FakeSite:
        items = [
            Listing("f1", "https://fake.ch/f1", "Flat, 3 rooms", location="47.3,8.5"),
            Listing("f2", "https://fake.ch/f2", "Flat without address"),
        ]
        return FakeSite(group(tmp_path), listings=items, commute=commute)

    first = site().collect()
    assert "ETH Zentrum: 20 min (Ben)" in first[0]["text"]
    assert "Commute" not in first[1]["text"]
    assert commute.lookups == 1 and commute.closed

    runner = site()
    again = runner.collect()
    assert commute.lookups == 1  # reused from the record
    assert "ETH Zentrum: 20 min" in again[0]["text"]
    assert runner.tracker.get("f1")["commute"].startswith("Commute")


def test_place_must_name_members(tmp_path) -> None:
    stranger = Place(name="Office", address="Somewhere 1, 8000 Zürich", who=["cleo"])
    with pytest.raises(ProfileError, match="cleo"):
        group(tmp_path, places=[stranger])


def test_flatfox_leaves_out_rooms_and_small_flats_for_groups(tmp_path) -> None:
    runner = FlatfoxRunner(group(tmp_path))
    flat = {"pk": 1, "object_category": "APARTMENT", "object_type": "APARTMENT"}
    runner.records = [
        {**flat, "number_of_rooms": "3.5", "latitude": 47.3, "longitude": 8.5},
        {**flat, "pk": 2, "number_of_rooms": "2.5"},
        {**flat, "pk": 3, "object_category": "SHARED", "object_type": "SHARED_FLAT"},
        {**flat, "pk": 4, "number_of_rooms": None},
    ]
    found = list(runner.listings())
    assert [item.id for item in found] == ["1", "4"]
    assert found[0].location == "47.3,8.5"


def test_woko_rooms_have_an_address() -> None:
    html = """
    <div class="crooms__element" data-price="600">
      <div class="crooms__text">Adresse</div><div class="crooms__text">Weg 1</div>
      <div class="crooms__text">Ort</div><div class="crooms__text">8046 Zürich</div>
      <a href="detail?oid=9">Detail</a>
      <a href="bewerbung-mietobjekt?oid=1&aid=9&type=0">Bewerben</a>
    </div>
    """
    html = html.replace('href="detail', 'href="freie-objekte/detail')
    assert parse_rooms(html, "https://w.ch/")[0]["address"] == "Weg 1, 8046 Zürich"
