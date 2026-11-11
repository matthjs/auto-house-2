"""
The digest: one email to the search's own members with the new drafts from every
site, so a daily batch run can be read without opening the records.

It only ever goes to members of the search (the emails in their person files), never
to landlords.
"""

import re
from typing import Any

from src.lib.tracker import Tracker, now
from src.search_profile import SearchProfile
from src.sites import SITES

DIGEST_STATUSES = ("shortlisted", "drafted", "needs_review")
FACT_LINE = re.compile(r"^[\w ()²/.-]{2,40}: .+")
MAX_FACTS = 8


def pending(
    profile: SearchProfile, min_fit: int
) -> list[tuple[Tracker, dict[str, Any]]]:
    """
    Find drafts that have not been in a digest yet.

    :param profile: The search.
    :param min_fit: Lowest fit score to include.
    :return: ``(tracker, record)`` pairs, best fit first.
    """
    found = []
    for runner in SITES.values():
        tracker = Tracker(profile.data_dir, runner.site)
        for record in tracker.records():
            score = (record.get("fit") or {}).get("score") or 0
            if (
                record["status"] in DIGEST_STATUSES
                and not record.get("notified_at")
                and score >= min_fit
            ):
                found.append((tracker, record))
    found.sort(key=lambda item: -((item[1].get("fit") or {}).get("score") or 0))
    return found


def recipients(profile: SearchProfile) -> list[str]:
    """
    Email addresses of the search's members.

    :param profile: The search.
    :return: Each member's ``Email``, in member order, without duplicates.
    """
    emails = [str(person.description.get("Email") or "") for person in profile.members]
    return list(dict.fromkeys(email for email in emails if "@" in email))


def facts(text: str) -> list[str]:
    """
    Pick the short ``Key: value`` lines (rent, rooms, address, ...) from a listing.

    :param text: Listing text.
    :return: Up to :data:`MAX_FACTS` lines.
    """
    lines = [line.strip() for line in text.splitlines()]
    return [line for line in lines if FACT_LINE.match(line)][:MAX_FACTS]


def format_entry(site: str, record: dict[str, Any]) -> str:
    """
    Describe one draft for the digest.

    :param site: Site name.
    :param record: The listing's record.
    :return: Plain text: fit, facts, commute, reasons, link and, if one was
        written, the draft.
    """
    fit = record.get("fit") or {}
    parts = [f"Fit {fit.get('score', '?')}/100 on {site}: {record.get('url', '')}"]
    parts += [f"  {line}" for line in facts(record.get("text", ""))]
    if record.get("commute"):
        parts += [f"  {line}" for line in record["commute"].splitlines()]
    parts += [f"  + {reason}" for reason in fit.get("reasons") or []]
    parts += [f"  ! {flag}" for flag in fit.get("red_flags") or []]
    if not record.get("response"):
        return "\n".join(parts)
    if record["status"] == "needs_review":
        issues = "; ".join(record.get("review_issues") or [])
        parts.append(f"  Draft needs a check before sending: {issues}")
    parts += [
        "",
        f"  Subject: {record.get('subject', '')}",
        "",
        *[f"  {line}" for line in str(record.get("response", "")).splitlines()],
    ]
    return "\n".join(parts)


def compose(
    profile: SearchProfile,
    items: list[tuple[Tracker, dict[str, Any]]],
    note: str | None = None,
) -> tuple[str, str]:
    """
    Write the digest email.

    :param profile: The search.
    :param items: Drafts from :func:`pending`.
    :param note: Extra line at the top, for example that this is a test.
    :return: Subject and plain-text body.
    """
    count = len(items)
    subject = f"auto-house: {count} new listing{'s' if count != 1 else ''}"
    intro = (
        f"New listings that fit the search '{profile.name}', best first. Nothing has "
        f"been sent to anyone. For a flat you like, ask the agent to write the "
        f"message, send it on the site yourself, then tell the agent it is sent."
    )
    entries = [format_entry(tracker.directory.name, rec) for tracker, rec in items]
    if note:
        intro = f"{note.strip()}\n\n{intro}"
    divider = "\n\n" + "-" * 60 + "\n\n"
    return subject, intro + divider + divider.join(entries) + "\n"


def mark_notified(items: list[tuple[Tracker, dict[str, Any]]]) -> None:
    """
    Remember that these drafts were in a digest, so they are not repeated.

    :param items: Drafts that were emailed.
    """
    timestamp = now()
    for tracker, record in items:
        tracker.update(record["id"], notified_at=timestamp)
