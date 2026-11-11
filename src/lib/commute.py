"""
Public transport travel times from a listing to the places a search cares about
(university, work), from the free Swiss timetable API at transport.opendata.ch.

No key is needed. Requests are made one at a time with a pause, and only for listings
that already passed the site's filters.
"""

import re
import time
from dataclasses import dataclass, field
from datetime import date, timedelta

import requests

from src.lib.logger import logger

API_URL = "https://transport.opendata.ch/v1/connections"
USER_AGENT = "Mozilla/5.0 (compatible; auto-house; personal housing search)"
REQUEST_DELAY_S = 1.0


@dataclass
class Place:
    """
    A place someone in the search travels to, for example a university building.
    """

    name: str
    address: str
    who: list[str] = field(default_factory=list)


def parse_duration(value: str) -> int:
    """
    Turn the API's duration into minutes.

    :param value: Duration such as ``00d00:26:00``.
    :return: Whole minutes, for example ``26``.
    :raises ValueError: If the value has another format.
    """
    match = re.fullmatch(r"(\d+)d(\d+):(\d+):(\d+)", value)
    if not match:
        raise ValueError(f"Unknown duration: {value}")
    days, hours, minutes, _ = (int(part) for part in match.groups())
    return days * 24 * 60 + hours * 60 + minutes


def next_weekday(today: date) -> date:
    """
    Pick the next Tuesday, a normal working day with the regular timetable.

    :param today: Today's date.
    :return: The first Tuesday after today.
    """
    return today + timedelta(days=(1 - today.weekday()) % 7 or 7)


class CommuteClient:
    """
    Look up the fastest public transport trip from a listing to each place.
    """

    def __init__(
        self,
        departure: str = "08:00",
        delay_s: float = REQUEST_DELAY_S,
        day: date | None = None,
    ) -> None:
        """
        Create an HTTP session.

        :param departure: Departure time on a weekday, ``HH:MM``.
        :param delay_s: Seconds to wait before each request after the first.
        :param day: Travel date; the next Tuesday by default.
        """
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.departure = departure
        self.day = day or next_weekday(date.today())
        self.delay_s = delay_s
        self._requested = False

    def minutes(self, origin: str, destination: str) -> int | None:
        """
        Find the shortest trip of the first few connections.

        :param origin: Coordinates ``lat,lng`` or an address such as
            ``Blumenfeldstrasse 104, 8046 Zürich``.
        :param destination: Address of the place.
        :return: Minutes door to door, or ``None`` if no trip was found.
        """
        if self._requested:
            time.sleep(self.delay_s)
        self._requested = True
        params = {
            "from": origin,
            "to": destination,
            "date": self.day.isoformat(),
            "time": self.departure,
            "limit": 3,
        }
        try:
            response = self.session.get(API_URL, params=params, timeout=30)
            response.raise_for_status()
            durations = [
                parse_duration(connection["duration"])
                for connection in response.json().get("connections", [])
                if connection.get("duration")
            ]
        except (requests.RequestException, ValueError, KeyError) as error:
            logger.warning(
                "Commute lookup %s -> %s failed: %s", origin, destination, error
            )
            return None
        return min(durations) if durations else None

    def describe(self, origin: str, places: list[Place], names: dict[str, str]) -> str:
        """
        Describe the commute from a listing to every place, for the listing text.

        :param origin: Where the listing is (coordinates or address).
        :param places: Places to travel to.
        :param names: Member file name -> display name, for ``Place.who``.
        :return: One line per place, under a heading; ``unknown`` where no trip was
            found.
        """
        lines = [f"Commute by public transport (weekday, leaving {self.departure}):"]
        for place in places:
            found = self.minutes(origin, place.address)
            duration = f"{found} min" if found is not None else "unknown"
            who = ", ".join(names.get(name, name) for name in place.who)
            lines.append(f"- {place.name}: {duration}" + (f" ({who})" if who else ""))
        return "\n".join(lines)

    def close(self) -> None:
        """
        Close the HTTP session.
        """
        self.session.close()
