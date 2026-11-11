"""
Shared fixtures: a throwaway profile, a scripted LLM and an in-memory site.
"""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import BaseModel

from src.agent import Draft, FitAssessment, Review
from src.lib.errors import SendError
from src.llm.base import LLMProvider, SchemaT
from src.personal_profile import PersonalProfile
from src.sites.base import Listing, SiteRunner

GOOD_MESSAGE = " ".join(["Hello, I am a student and would love to live here."] * 8)


@pytest.fixture
def profile(tmp_path: Path) -> PersonalProfile:
    """
    Write a complete profile to a temporary ``secret/`` folder and load it.

    :param tmp_path: Pytest's temporary directory.
    :return: The loaded profile.
    """
    directory = tmp_path / "secret" / "tester"
    directory.mkdir(parents=True)
    files = {
        "my_description.json": {
            "Name": "Test Student",
            "Phone_number": "+41 00 000 00 00",
            "Email": "student@example.com",
            "Occupation": "MSc student",
        },
        "living_preferences.json": {
            "place_wg_zimmer": "zurich-stadt",
            "place": "Zurich",
            "budget_upper_bound": "920",
            "deal_breakers": "",
        },
        "site_credentials.json": {
            "flatfox_login": "",
            "login": "me@gmail.com",
            "password": "app-password",
            "DeepSeek_API_KEY": "from-json",
        },
    }
    for name, content in files.items():
        (directory / name).write_text(json.dumps(content), encoding="utf-8")
    return PersonalProfile("tester", secret_dir=tmp_path / "secret")


def fit(score: int = 85, recommendation: str = "apply") -> FitAssessment:
    """
    Build a fit assessment.

    :param score: Fit score.
    :param recommendation: ``apply`` or ``skip``.
    :return: The assessment.
    """
    return FitAssessment(
        score=score,
        recommendation=recommendation,
        language="English",
        reasons=["Within budget"],
        red_flags=[],
    )


def draft(message: str = GOOD_MESSAGE) -> Draft:
    """
    Build a draft.

    :param message: Message body.
    :return: The draft.
    """
    return Draft(recipient_analysis="A flatshare.", subject="Room", message=message)


class ScriptedLLM(LLMProvider):
    """
    LLM that returns queued answers per schema and records every prompt.
    """

    name = "scripted"

    def __init__(self, answers: dict[type[BaseModel], list[BaseModel]]) -> None:
        """
        Queue answers.

        :param answers: For each schema, the answers to return in order.
        """
        super().__init__("scripted-model", None)
        self.answers = {schema: list(queue) for schema, queue in answers.items()}
        self.calls: list[tuple[type[BaseModel], str]] = []

    def generate(self, system: str, prompt: str, schema: type[SchemaT]) -> SchemaT:
        """
        Pop the next queued answer for ``schema``.

        :param system: Ignored.
        :param prompt: Recorded for assertions.
        :param schema: Which queue to pop from.
        :return: The queued answer.
        """
        self.calls.append((schema, prompt))
        return self.answers[schema].pop(0)


def scripted(
    fits: list[FitAssessment] | None = None,
    drafts: list[Draft] | None = None,
    reviews: list[Review] | None = None,
) -> ScriptedLLM:
    """
    Build a scripted LLM with sensible defaults (apply, good draft, passed review).

    :param fits: Fit answers.
    :param drafts: Draft answers.
    :param reviews: Review answers.
    :return: The LLM.
    """
    return ScriptedLLM(
        {
            FitAssessment: fits or [fit()] * 10,
            Draft: drafts or [draft()] * 10,
            Review: reviews or [Review(passed=True, issues=[])] * 10,
        }
    )


class FakeSite(SiteRunner):
    """
    Site runner over a fixed list of listings that records what it sends.
    """

    site = "fake.ch"

    def __init__(self, *args, listings: list[Listing], fail_send: bool = False, **kw):
        """
        Set up the fake site.

        :param args: Passed to :class:`SiteRunner`.
        :param listings: Listings to yield.
        :param fail_send: Make every send raise :class:`SendError`.
        :param kw: Passed to :class:`SiteRunner`.
        """
        super().__init__(*args, **kw)
        self._listings = listings
        self.fail_send = fail_send
        self.sent: list[tuple[str, str, str]] = []
        self.closed = False

    def required_fields(self) -> tuple[str, ...]:
        """
        Need nothing.

        :return: Empty tuple.
        """
        return ()

    def start(self) -> None:
        """
        Nothing to open.
        """

    def listings(self) -> Iterator[Listing]:
        """
        Yield the fixed listings.

        :return: Iterator over listings.
        """
        yield from self._listings

    def send(self, listing: Listing, subject: str, message: str) -> None:
        """
        Record the message, or fail if configured to.

        :param listing: The listing.
        :param subject: Subject.
        :param message: Body.
        :raises SendError: If ``fail_send`` is set.
        """
        if self.fail_send:
            raise SendError("site down")
        self.sent.append((listing.id, subject, message))

    def close(self) -> None:
        """
        Remember that close was called.
        """
        self.closed = True


def listing(listing_id: str = "a1", email: str | None = None) -> Listing:
    """
    Build a listing.

    :param listing_id: Listing id.
    :param email: Contact email.
    :return: The listing.
    """
    return Listing(
        id=listing_id,
        url=f"https://fake.ch/{listing_id}",
        content="<p>Room, 800 CHF</p>",
        contact_email=email,
    )
