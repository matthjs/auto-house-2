"""
Tests for the shared run loop: modes, send caps, failures and reuse of drafts.
"""

import json

from src.agent import ApplicationAgent, Review
from tests.conftest import FakeSite, fit, listing, scripted


def make_site(profile, listings, llm=None, **kw) -> FakeSite:
    """
    Build a fake site with an agent around a scripted LLM.

    :param profile: Profile fixture.
    :param listings: Listings to yield.
    :param llm: LLM to use; defaults to one that always applies.
    :param kw: Extra :class:`FakeSite` arguments.
    :return: The site runner.
    """
    agent = ApplicationAgent(profile, llm or scripted())
    return FakeSite(profile, agent, listings=listings, **kw)


def test_dry_run_never_sends(profile) -> None:
    site = make_site(profile, [listing("a"), listing("b")])
    summary = site.run()
    assert site.sent == []
    assert summary["drafted"] == 2
    assert site.tracker.get("a")["status"] == "drafted"
    assert site.closed


def test_auto_sends_at_most_max_sends(profile) -> None:
    site = make_site(
        profile, [listing(str(i)) for i in range(5)], mode="auto", max_sends=2
    )
    summary = site.run()
    assert len(site.sent) == 2 and summary["sent"] == 2


def test_auto_does_not_send_drafts_that_fail_review(profile) -> None:
    llm = scripted(reviews=[Review(passed=False, issues=["Invented a job."])] * 4)
    site = make_site(profile, [listing("a")], llm=llm, mode="auto")
    site.run()
    assert site.sent == []
    assert site.tracker.get("a")["status"] == "needs_review"


def test_failed_send_is_not_marked_contacted(profile) -> None:
    site = make_site(profile, [listing("a")], mode="auto", fail_send=True)
    site.run()
    record = site.tracker.get("a")
    assert record["status"] == "failed" and "site down" in record["error"]
    assert not site.tracker.is_done("a")


def test_handled_listings_are_skipped_including_legacy_records(profile) -> None:
    site = make_site(profile, [listing("old"), listing("new")])
    legacy = site.tracker.path("old")
    legacy.write_text(json.dumps({"id": "old", "subject": "s", "response": "r"}))
    summary = site.run()
    assert summary["already_handled"] == 1
    assert site.tracker.get("old")["status"] == "sent"


def test_skipped_listing_is_final(profile) -> None:
    site = make_site(profile, [listing("a")], llm=scripted(fits=[fit(10, "skip")]))
    site.run()
    assert site.tracker.is_done("a")


def test_missing_contact_email_skips_without_llm(profile) -> None:
    llm = scripted()
    site = make_site(profile, [listing("a", email=None)], llm=llm)
    site.needs_contact_email = True
    site.run()
    assert llm.calls == []
    assert site.tracker.get("a")["status"] == "skipped"


def test_confirm_mode_sends_the_edited_draft(profile) -> None:
    def ask(_question: str) -> str:
        path = site.tracker.directory / "_review.json"
        content = json.loads(path.read_text())
        content["response"] = "Edited by me."
        path.write_text(json.dumps(content))
        return "s"

    site = make_site(profile, [listing("a")], mode="confirm", ask=ask)
    site.run()
    assert site.sent == [("a", "Room", "Edited by me.")]
    assert not (site.tracker.directory / "_review.json").exists()


def test_confirm_quit_stops_and_keeps_the_draft(profile) -> None:
    site = make_site(
        profile, [listing("a"), listing("b")], mode="confirm", ask=lambda _: "q"
    )
    summary = site.run()
    assert summary["drafted"] == 1 and site.sent == []
    assert site.tracker.get("b") is None
    assert site.closed


def test_saved_draft_is_reused_without_llm_calls(profile) -> None:
    make_site(profile, [listing("a")]).run()
    llm = scripted()
    site = make_site(profile, [listing("a")], llm=llm, mode="auto")
    site.run()
    assert llm.calls == []
    assert site.sent and site.tracker.get("a")["status"] == "sent"
    assert [h["status"] for h in site.tracker.get("a")["history"]] == [
        "drafted",
        "sent",
    ]
