"""
The loop shared by all sites: find listings, record them, and (in batch mode) let the
built-in agent draft and, if allowed, send.
"""

from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from src.agent import AgentResult, ApplicationAgent, html_to_text
from src.lib.commute import CommuteClient
from src.lib.email_client import EmailError
from src.lib.errors import SendError
from src.lib.logger import logger
from src.lib.tracker import Tracker
from src.llm.base import LLMError
from src.search_profile import SearchProfile


@dataclass
class Listing:
    """
    One housing offer as scraped from a site.
    """

    id: str
    url: str
    content: str
    contact_email: str | None = None
    location: str | None = None


class SiteRunner(ABC):
    """
    Search one site and handle its listings.

    Subclasses implement the site-specific steps (:meth:`start`, :meth:`listings`,
    :meth:`send`, :meth:`close`). Two ways to use a runner:

    - :meth:`collect` (``command=search``): save new listings and return them, so a
      coding agent or the user can evaluate and draft them.
    - :meth:`run` (``command=run``, batch mode): the built-in LLM agent evaluates and
      drafts each new listing. With ``dry_run`` (default) nothing is sent; without
      it, drafts that passed review are sent, at most ``max_sends`` per run, on sites
      that allow sending (:attr:`can_send`).

    Listings with a final status (sent, rejected, skipped) are never processed again.
    """

    site: str = ""
    needs_contact_email: bool = False
    can_send: bool = True

    def __init__(
        self,
        profile: SearchProfile,
        agent: ApplicationAgent | None = None,
        dry_run: bool = True,
        max_sends: int = 5,
        options: dict[str, Any] | None = None,
        commute: CommuteClient | None = None,
    ) -> None:
        """
        Prepare a run.

        :param profile: The search.
        :param agent: Agent for batch mode; not needed for :meth:`collect`.
        :param dry_run: Never send anything.
        :param max_sends: Most messages to send in one batch run.
        :param options: Site settings from ``conf/site/<site>.yaml``.
        :param commute: Looks up travel times to the search's places for listings
            with a :attr:`Listing.location`; ``None`` turns this off.
        """
        self.profile = profile
        self.commute = commute
        self.agent = agent
        self.dry_run = dry_run
        self.max_sends = max_sends
        self.options = options or {}
        self.tracker = Tracker(profile.data_dir, self.site)
        self.summary: Counter[str] = Counter()
        self._commutes: dict[str, str] = {}

    @abstractmethod
    def required_fields(self) -> tuple[str, ...]:
        """
        Profile fields needed to search this site.

        :return: Attribute names of :class:`SearchProfile`.
        """

    def send_fields(self) -> tuple[str, ...]:
        """
        Profile fields needed to send a message on this site.

        :return: Attribute names of :class:`SearchProfile`; none by default.
        """
        return ()

    @abstractmethod
    def start(self) -> None:
        """
        Open the browser or session, log in if needed, and run the search.
        """

    @abstractmethod
    def listings(self) -> Iterator[Listing]:
        """
        Yield the search results one by one.

        :return: Iterator over listings.
        """

    def send(self, listing: Listing, subject: str, message: str) -> None:
        """
        Deliver a message for a listing.

        :param listing: The listing being answered.
        :param subject: Subject line (ignored by sites without one).
        :param message: Message body.
        :raises SendError: If the site does not support or accept the message.
        :raises EmailError: If sending by email fails.
        """
        raise SendError(f"{self.site} messages have to be sent by hand")

    @abstractmethod
    def close(self) -> None:
        """
        Close the browser or session. Must be safe to call even if :meth:`start`
        failed.
        """

    def _new_listings(self) -> Iterator[Listing]:
        """
        Start the site and yield listings that are not handled for good yet.

        :return: Iterator over open listings; the site is closed afterwards.
        :raises ProfileError: If a required profile field is empty.
        """
        self.profile.require(*self.required_fields())
        try:
            self.start()
            for listing in self.listings():
                if self.tracker.is_done(listing.id):
                    self.summary["already_handled"] += 1
                    continue
                yield self._with_commute(listing)
        finally:
            self.close()
            if self.commute is not None:
                self.commute.close()

    def _with_commute(self, listing: Listing) -> Listing:
        """
        Add travel times to the search's places to the listing text.

        Times are looked up once per listing and kept in its record, so later
        searches make no new requests.

        :param listing: A listing to be handled.
        :return: The listing, with a commute section appended when known.
        """
        if self.commute is None or not listing.location or not self.profile.places:
            return listing
        record = self.tracker.get(listing.id)
        commute = record.get("commute") if record else None
        if not commute:
            commute = self.commute.describe(
                listing.location, self.profile.places, self.profile.display_names()
            )
            if record is not None:
                self.tracker.update(listing.id, commute=commute)
        self._commutes[listing.id] = commute
        listing.content = f"{listing.content}\n\n{commute}"
        return listing

    def collect(self) -> list[dict[str, Any]]:
        """
        Save every open listing as ``found`` (keeping any draft) and return them.

        :return: One dict per listing: site, id, url, text and contact email.
        """
        found = []
        for listing in self._new_listings():
            text = html_to_text(listing.content)
            record = self.tracker.get(listing.id)
            status = record["status"] if record else "found"
            if record is None:
                self._record(listing, status, text=text)
            found.append(
                {
                    "site": self.site,
                    "id": listing.id,
                    "url": listing.url,
                    "status": status,
                    "contact_email": listing.contact_email,
                    "text": text,
                }
            )
        logger.info("Found %d open listings on %s", len(found), self.site)
        return found

    def run(self) -> Counter[str]:
        """
        Batch mode: let the built-in agent handle every open listing.

        :return: How many listings ended in each outcome.
        :raises ProfileError: If a required profile field is empty.
        """
        if self.agent is None:
            raise ValueError("Batch mode needs an agent")
        if not self.dry_run and self.can_send:
            self.profile.require(*self.send_fields())
        for listing in self._new_listings():
            self.handle(listing)
            if self.summary["sent"] >= self.max_sends:
                logger.info("Reached max_sends=%d; stopping", self.max_sends)
                break
        logger.info("Run summary for %s: %s", self.site, dict(self.summary))
        return self.summary

    def handle(self, listing: Listing) -> None:
        """
        Evaluate, draft and possibly send one listing, and record the outcome.

        :param listing: A listing that has not been handled for good yet.
        """
        if self.needs_contact_email and not listing.contact_email:
            self._record(listing, "skipped", reason="No contact email on the listing")
            return

        record = self.tracker.get(listing.id)
        if record and record["status"] == "shortlisted" and not self.agent.write_drafts:
            self.summary["already_judged"] += 1
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
            if result.draft is None:
                self._record(listing, "shortlisted", **draft)
                return

        ready = not draft.get("review_issues")
        if ready and not self.dry_run and self.can_send:
            self._send(listing, draft)
        else:
            self._record(listing, "drafted" if ready else "needs_review", **draft)

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
        extra: dict[str, Any] = (
            {"contact_email": listing.contact_email} if listing.contact_email else {}
        )
        if listing.id in self._commutes:
            extra["commute"] = self._commutes[listing.id]
        record = self.tracker.get(listing.id)
        has_text = "text" in fields or (record and record.get("text"))
        if listing.content and not has_text:
            extra["text"] = html_to_text(listing.content)
        self.tracker.save(listing.id, status, url=listing.url, **extra, **fields)
        self.summary[status] += 1
