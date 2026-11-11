"""
The application agent: decide whether a listing fits, draft a message, and check it.
"""

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from src.lib.logger import logger
from src.llm.base import LLMProvider
from src.search_profile import SearchProfile

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
PLACEHOLDER_PATTERN = re.compile(r"\[[^\]]*\]|\{[^}]*\}|\bX{3,}\b|\bTODO\b|<[^>]+>")
MIN_WORDS = 40
MAX_WORDS = 350
BLOCK_TAGS = {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "table", "section"}


class FitAssessment(BaseModel):
    """
    The agent's verdict on whether a listing is worth applying to.
    """

    score: int
    recommendation: Literal["apply", "skip"]
    language: str
    reasons: list[str]
    red_flags: list[str]


class Draft(BaseModel):
    """
    A drafted message, with the analysis of the recipient that led to it.
    """

    recipient_analysis: str
    subject: str
    message: str


class Review(BaseModel):
    """
    The result of checking a draft before it is sent.
    """

    passed: bool
    issues: list[str]


@dataclass
class AgentResult:
    """
    Everything the agent produced for one listing.

    ``draft`` and ``review`` are ``None`` when the listing was skipped, or when it
    fits but the agent only judges (``write_drafts=False``).
    """

    assessment: FitAssessment
    draft: Draft | None = None
    review: Review | None = None
    attempts: int = 0
    fits: bool = False

    @property
    def should_apply(self) -> bool:
        """
        Whether the listing is worth applying to.

        :return: ``True`` if the fit check recommends it at or above ``min_fit``.
        """
        return self.fits

    @property
    def ready_to_send(self) -> bool:
        """
        Whether the final draft passed review.

        :return: ``True`` if there is a draft and its review passed.
        """
        return self.draft is not None and self.review is not None and self.review.passed


class _TextExtractor(HTMLParser):
    """
    Collect the visible text of an HTML fragment.
    """

    def __init__(self) -> None:
        """
        Start with an empty buffer.
        """
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        """
        Track script/style blocks and break lines at block elements.

        :param tag: Tag name.
        :param attrs: Tag attributes (unused).
        """
        if tag in {"script", "style"}:
            self._skip_depth += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        """
        Close script/style blocks and break lines at block elements.

        :param tag: Tag name.
        """
        if tag in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")
        elif tag == "td":
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        """
        Keep text that is not inside script/style.

        :param data: Text between tags.
        """
        if not self._skip_depth:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    """
    Turn listing HTML into compact plain text for the prompt.

    Plain text (without tags) passes through with only whitespace cleaned up.

    :param html: HTML fragment or plain text.
    :return: Visible text, one block per line, without blank runs.
    """
    extractor = _TextExtractor()
    extractor.feed(html)
    extractor.close()
    lines = (
        re.sub(r"[ \t\r\f\v]+", " ", line).strip()
        for line in "".join(extractor.parts).splitlines()
    )
    return "\n".join(line for line in lines if line)


def local_issues(draft: Draft) -> list[str]:
    """
    Check a draft for problems that need no LLM to spot.

    :param draft: Draft to check.
    :return: One sentence per problem; empty if the draft looks fine.
    """
    issues = []
    if not draft.subject.strip():
        issues.append("The subject is empty.")
    placeholders = PLACEHOLDER_PATTERN.findall(f"{draft.subject}\n{draft.message}")
    if placeholders:
        issues.append(
            f"Remove placeholders or markup: {', '.join(sorted(set(placeholders)))}."
        )
    words = len(draft.message.split())
    if words < MIN_WORDS:
        issues.append(f"The message is too short ({words} words).")
    if words > MAX_WORDS:
        issues.append(f"The message is too long ({words} words); keep it under 200.")
    return issues


def load_prompt(name: str) -> str:
    """
    Read a system prompt from the ``prompts/`` folder.

    :param name: File name without ``.md``.
    :return: The prompt text.
    """
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def wrap_listing(text: str) -> str:
    """
    Enclose untrusted listing text in ``<listing>`` tags.

    Any ``listing`` tags already in the text are removed, so the listing cannot close
    the block early and pose as instructions.

    :param text: Listing text.
    :return: The text inside ``<listing>`` tags.
    """
    cleaned = re.sub(r"</?listing>", "", text, flags=re.IGNORECASE)
    return f"<listing>\n{cleaned}\n</listing>"


class ApplicationAgent:
    """
    Evaluate a listing, draft a message if it fits, and review the draft.

    A draft that fails review is rewritten with the review's feedback, up to
    ``max_attempts`` drafts in total. The agent never sends anything; the run loop
    decides that.
    """

    def __init__(
        self,
        profile: SearchProfile,
        llm: LLMProvider,
        min_fit: int = 60,
        max_attempts: int = 2,
        write_drafts: bool = True,
    ) -> None:
        """
        Set up the agent for one user.

        :param profile: Whose application this is.
        :param llm: Provider used for every step.
        :param min_fit: Lowest fit score (0-100) to apply at.
        :param max_attempts: Maximum number of drafts per listing.
        :param write_drafts: Write and review a message for listings that fit; when
            ``False`` the agent only judges the fit.
        """
        self.profile = profile
        self.llm = llm
        self.min_fit = min_fit
        self.max_attempts = max_attempts
        self.write_drafts = write_drafts
        self.prompts = {
            name: load_prompt(name) for name in ("evaluate", "draft", "review")
        }

    def process(self, listing_text: str) -> AgentResult:
        """
        Run the evaluate-draft-review loop for one listing.

        :param listing_text: Listing HTML or text as scraped.
        :return: The assessment and, if the listing fits and drafts are on, the final
            draft and review.
        :raises LLMError: If a provider call fails.
        """
        listing = wrap_listing(html_to_text(listing_text))
        assessment = self.evaluate(listing)
        result = AgentResult(assessment=assessment)
        if assessment.recommendation != "apply" or assessment.score < self.min_fit:
            return result
        result.fits = True
        if not self.write_drafts:
            return result

        feedback: list[str] = []
        while result.attempts < self.max_attempts:
            result.attempts += 1
            result.draft = self.draft(listing, assessment, feedback)
            result.review = self.review(listing, assessment, result.draft)
            if result.review.passed:
                break
            feedback = result.review.issues
            logger.info(
                "Draft %d failed review: %s", result.attempts, "; ".join(feedback)
            )
        return result

    def evaluate(self, listing: str) -> FitAssessment:
        """
        Score how well the listing fits the user.

        :param listing: Listing text, already wrapped by :func:`wrap_listing`.
        :return: The fit assessment.
        """
        prompt = (
            f"Applicant's preferences:\n{self.profile.preferences_text()}\n\n"
            f"Applicant's description:\n{self.profile.description_text()}\n\n"
            f"{listing}"
        )
        return self.llm.generate(self.prompts["evaluate"], prompt, FitAssessment)

    def draft(
        self, listing: str, assessment: FitAssessment, feedback: list[str]
    ) -> Draft:
        """
        Write a message to the person offering the listing.

        :param listing: Listing text, already wrapped by :func:`wrap_listing`.
        :param assessment: Fit assessment, used for the language and talking points.
        :param feedback: Issues found in the previous draft; empty on the first try.
        :return: The draft.
        """
        prompt = (
            f"Write in: {assessment.language}\n\n"
            f"Applicant's description:\n{self.profile.description_text()}\n\n"
            f"Why this listing fits:\n"
            + "\n".join(f"- {r}" for r in assessment.reasons)
            + f"\n\n{listing}"
        )
        if feedback:
            prompt += "\n\nReviewer feedback on the previous draft:\n" + "\n".join(
                f"- {issue}" for issue in feedback
            )
        return self.llm.generate(self.prompts["draft"], prompt, Draft)

    def review(self, listing: str, assessment: FitAssessment, draft: Draft) -> Review:
        """
        Check a draft with fast local rules first, then with the LLM.

        The LLM is only asked when the local rules pass.

        :param listing: Listing text, already wrapped by :func:`wrap_listing`.
        :param assessment: Fit assessment, for the expected language.
        :param draft: Draft to check.
        :return: The review; ``passed`` is ``False`` if any issue was found.
        """
        issues = local_issues(draft)
        if issues:
            return Review(passed=False, issues=issues)
        prompt = (
            f"Expected language: {assessment.language}\n\n"
            f"Applicant's description:\n{self.profile.description_text()}\n\n"
            f"{listing}\n\n"
            f"Draft subject: {draft.subject}\n\nDraft message:\n{draft.message}"
        )
        review = self.llm.generate(self.prompts["review"], prompt, Review)
        # Never trust passed=True alongside listed issues.
        return Review(passed=review.passed and not review.issues, issues=review.issues)
