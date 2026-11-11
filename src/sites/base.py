"""
The run loop shared by all sites: find listings, let the agent decide, then send.
"""

from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, Literal

from src.agent import AgentResult, ApplicationAgent
from src.lib.email_client import EmailError
from src.lib.errors import SendError
from src.lib.logger import logger
from src.lib.tracker import Tracker
from src.llm.base import LLMError
from src.personal_profile import PersonalProfile

Mode = Literal["dry-run", "confirm", "auto"]
MODES: tuple[Mode, ...] = ("dry-run", "confirm", "auto")
REVIEW_FILE = "review"


@dataclass
class Listing:
    """
    One housing offer as scraped from a site.
    """

    id: str
    url: str
    content: str
    contact_email: str | None = None


class StopRun(Exception):
    """
    Raised when the user asks to stop during confirmation.
    """


class SiteRunner(ABC):
    """
    Run the agent over one site's search results.

    Subclasses implement the site-specific steps (:meth:`start`, :meth:`listings`,
    :meth:`send`, :meth:`close`). This class decides what happens to each listing:

    - ``dry-run`` (default): evaluate and draft, save the result, never send.
    - ``confirm``: show each passing draft, let the user edit it, and send only on
      an explicit yes.
    - ``auto``: send drafts that passed review, at most ``max_sends`` per run.

    Listings with a final status (sent, rejected, skipped) are never processed again.
    A draft saved by an earlier run is reused instead of being written again.
    """

    site: str = ""
    needs_contact_email: bool = False

    def __init__(
        self,
        profile: PersonalProfile,
        agent: ApplicationAgent,
        mode: Mode = "dry-run",
        max_sends: int = 5,
        ask: Callable[[str], str] = input,
    ) -> None:
        """
        Prepare a run.

        :param profile: Whose search this is.
        :param agent: Agent that evaluates and drafts.
        :param mode: ``dry-run``, ``confirm`` or ``auto``.
        :param max_sends: Most messages to send in one run (``auto`` mode).
        :param ask: Function that asks the user a question; replaced in tests.
        :raises ValueError: If ``mode`` is unknown.
        """
        if mode not in MODES:
            raise ValueError(f"Unknown mode '{mode}'. Choose from: {', '.join(MODES)}")
        self.profile = profile
        self.agent = agent
        self.mode = mode
        self.max_sends = max_sends
        self.ask = ask
        self.tracker = Tracker(profile.data_dir, self.site)
        self.summary: Counter[str] = Counter()

    @abstractmethod
    def required_fields(self) -> tuple[str, ...]:
        """
        Profile fields this site needs in the current mode.

        :return: Attribute names of :class:`PersonalProfile`.
        """

    @abstractmethod
    def start(self) -> None:
        """
        Open the browser, log in and run the search.
        """

    @abstractmethod
    def listings(self) -> Iterator[Listing]:
        """
        Yield the search results one by one.

        The browser stays on a listing's page until the next one is requested, so
        :meth:`send` can act on the current page.

        :return: Iterator over listings.
        """

    @abstractmethod
    def send(self, listing: Listing, subject: str, message: str) -> None:
        """
        Deliver a message for a listing.

        :param listing: The listing being answered.
        :param subject: Subject line (ignored by sites without one).
        :param message: Message body.
        :raises SendError: If the site does not accept the message.
        :raises EmailError: If sending by email fails.
        """

    @abstractmethod
    def close(self) -> None:
        """
        Close the browser. Must be safe to call even if :meth:`start` failed.
        """

    def run(self) -> Counter[str]:
        """
        Process every new listing, then close the browser.

        :return: How many listings ended in each outcome.
        :raises ProfileError: If a required profile field is empty.
        """
        self.profile.require(*self.required_fields())
        try:
            self.start()
            for listing in self.listings():
                if self.tracker.is_done(listing.id):
                    logger.info("Skipping %s: already handled", listing.id)
                    self.summary["already_handled"] += 1
                    continue
                self.handle(listing)
                if self.mode == "auto" and self.summary["sent"] >= self.max_sends:
                    logger.info("Reached --max-sends=%d; stopping", self.max_sends)
                    break
        except StopRun:
            logger.info("Stopped by user")
        finally:
            self.close()
        logger.info("Run summary for %s: %s", self.site, dict(self.summary))
        return self.summary

    def handle(self, listing: Listing) -> None:
        """
        Decide what to do with one listing and record the outcome.

        :param listing: A listing that has not been handled for good yet.
        :raises StopRun: If the user asks to stop.
        """
        if self.needs_contact_email and not listing.contact_email:
            self._record(listing, "skipped", reason="No contact email on the listing")
            return

        draft = self._saved_draft(listing)
        if draft is None:
            try:
                result = self.agent.process(listing.content)
            except LLMError as error:
                logger.error("LLM failed for %s: %s", listing.id, error)
                self._record(listing, "failed", error=str(error))
                return
            draft = self._draft_fields(result)
            if not result.should_apply:
                self._record(listing, "skipped", **draft)
                return

        ready = not draft.get("review_issues")
        if self.mode == "dry-run":
            self._record(listing, "drafted" if ready else "needs_review", **draft)
        elif self.mode == "auto":
            if ready:
                self._send(listing, draft)
            else:
                self._record(listing, "needs_review", **draft)
        else:
            self._confirm(listing, draft)

    def _saved_draft(self, listing: Listing) -> dict[str, Any] | None:
        """
        Reuse a draft from an earlier run, so it is not paid for twice.

        :param listing: The listing.
        :return: Stored draft fields, or ``None`` if there is no usable draft.
        """
        record = self.tracker.get(listing.id)
        if record and record["status"] in {"drafted", "needs_review"}:
            if record.get("response"):
                logger.info("Reusing saved draft for %s", listing.id)
                keys = (
                    "fit",
                    "subject",
                    "response",
                    "recipient_analysis",
                    "review_issues",
                )
                return {key: record.get(key) for key in keys}
        return None

    @staticmethod
    def _draft_fields(result: AgentResult) -> dict[str, Any]:
        """
        Turn the agent's result into the fields stored in a record.

        :param result: The agent's result.
        :return: Fit assessment and, if any, the draft and its review issues.
        """
        fields: dict[str, Any] = {"fit": result.assessment.model_dump()}
        if result.draft is not None:
            fields.update(
                subject=result.draft.subject,
                response=result.draft.message,
                recipient_analysis=result.draft.recipient_analysis,
                review_issues=result.review.issues if result.review else [],
            )
        return fields

    def _confirm(self, listing: Listing, draft: dict[str, Any]) -> None:
        """
        Let the user edit the draft and choose to send, reject or postpone it.

        :param listing: The listing.
        :param draft: Draft fields.
        :raises StopRun: If the user chooses to quit.
        """
        fit = draft.get("fit") or {}
        path = self.tracker.write_working_file(
            REVIEW_FILE,
            {
                "url": listing.url,
                "fit_score": fit.get("score"),
                "reasons": fit.get("reasons", []),
                "red_flags": fit.get("red_flags", []),
                "review_issues": draft.get("review_issues", []),
                "subject": draft.get("subject", ""),
                "response": draft.get("response", ""),
            },
        )
        reasons = "; ".join(fit.get("reasons", []))
        print(f"\n{listing.url}\nFit {fit.get('score')}/100: {reasons}")
        if fit.get("red_flags"):
            print(f"Red flags: {'; '.join(fit['red_flags'])}")
        if draft.get("review_issues"):
            print(f"Review issues: {'; '.join(draft['review_issues'])}")
        print(f"Edit the draft in {path} if needed.")

        while True:
            answer = self.ask("[s]end / [r]eject / [l]ater / [q]uit: ").strip().lower()
            if answer[:1] in {"s", "r", "l", "q"}:
                break
        edited = self.tracker.read_working_file(REVIEW_FILE)
        draft = {
            **draft,
            "subject": edited.get("subject", ""),
            "response": edited.get("response", ""),
        }

        if answer.startswith("s"):
            self._send(listing, draft)
        elif answer.startswith("r"):
            self._record(listing, "rejected", **draft)
        else:
            self._record(
                listing,
                "needs_review" if draft.get("review_issues") else "drafted",
                **draft,
            )
            if answer.startswith("q"):
                raise StopRun

    def _send(self, listing: Listing, draft: dict[str, Any]) -> None:
        """
        Send a draft and record ``sent``, or ``failed`` if delivery fails.

        :param listing: The listing.
        :param draft: Draft fields with ``subject`` and ``response``.
        """
        if not str(draft.get("response", "")).strip():
            self._record(
                listing, "needs_review", error="Empty message; not sent", **draft
            )
            return
        try:
            self.send(listing, draft.get("subject", ""), draft["response"])
        except (SendError, EmailError) as error:
            logger.error("Sending to %s failed: %s", listing.id, error)
            self._record(listing, "failed", error=str(error), **draft)
            return
        self._record(listing, "sent", **draft)

    def _record(self, listing: Listing, status: str, **fields: Any) -> None:
        """
        Save a listing's outcome and count it in the run summary.

        :param listing: The listing.
        :param status: Outcome status.
        :param fields: Extra fields to store.
        """
        extra = (
            {"contact_email": listing.contact_email} if listing.contact_email else {}
        )
        self.tracker.save(listing.id, status, url=listing.url, **extra, **fields)
        self.summary[status] += 1
        logger.info("%s: %s", listing.id, status)
