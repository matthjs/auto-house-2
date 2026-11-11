"""
Tests for the shared site loop: collect, batch mode, dry run, caps and failures.
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


def test_collect_saves_found_listings_and_contacts_nobody(profile) -> None:
    site = make_site(profile, [listing("a"), listing("b")])
    found = site.collect()
    assert [item["id"] for item in found] == ["a", "b"]
    assert found[0]["text"] == "Room, 800 CHF"
    assert site.tracker.get("a")["status"] == "found"
    assert site.sent == [] and site.closed


def test_collect_twice_keeps_one_history_entry(profile) -> None:
    make_site(profile, [listing("a")]).collect()
    site = make_site(profile, [listing("a")])
    site.collect()
    assert len(site.tracker.get("a")["history"]) == 1


def test_batch_dry_run_never_sends(profile) -> None:
    site = make_site(profile, [listing("a"), listing("b")])
    summary = site.run()
    assert site.sent == []
    assert summary["drafted"] == 2
    assert site.tracker.get("a")["status"] == "drafted"
    assert site.closed


def test_batch_sends_at_most_max_sends(profile) -> None:
    listings = [listing(str(i)) for i in range(5)]
    site = make_site(profile, listings, dry_run=False, max_sends=2)
    summary = site.run()
    assert len(site.sent) == 2 and summary["sent"] == 2


def test_draft_only_site_never_sends(profile) -> None:
    site = make_site(profile, [listing("a")], dry_run=False)
    site.can_send = False
    site.run()
    assert site.sent == []
    assert site.tracker.get("a")["status"] == "drafted"


def test_batch_does_not_send_drafts_that_fail_review(profile) -> None:
    llm = scripted(reviews=[Review(passed=False, issues=["Invented a job."])] * 4)
    site = make_site(profile, [listing("a")], llm=llm, dry_run=False)
    site.run()
    assert site.sent == []
    assert site.tracker.get("a")["status"] == "needs_review"


def test_failed_send_is_not_marked_contacted(profile) -> None:
    site = make_site(profile, [listing("a")], dry_run=False, fail_send=True)
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


def test_saved_draft_is_reused_without_llm_calls(profile) -> None:
    make_site(profile, [listing("a")]).run()
    llm = scripted()
    site = make_site(profile, [listing("a")], llm=llm, dry_run=False)
    site.run()
    assert llm.calls == []
    assert site.sent and site.tracker.get("a")["status"] == "sent"
    history = [h["status"] for h in site.tracker.get("a")["history"]]
    assert history == ["drafted", "sent"]
