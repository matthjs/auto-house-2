"""
Tests for the profile, tracker, email parsing, scraper helpers and providers.
"""

import email
from types import SimpleNamespace

import pytest

from src.agent import FitAssessment
from src.lib.email_client import extract_otp, message_text
from src.lib.tracker import Tracker
from src.lib.wg_zimmer_client import listing_id, parse_listing, parse_results
from src.lib.wohnen_ethz_web_interactor import pick_contact_email
from src.llm import DEFAULT_MODELS, LLMError, create_provider
from src.search_profile import Person, ProfileError, SearchProfile
from tests.conftest import fit


def test_profile_loads_budget_and_description(profile) -> None:
    assert profile.max_rent == 920
    assert not profile.is_group
    assert "Name: Test Student" in profile.description_text()
    assert profile.preferences_text().startswith("people: 1")


def test_group_search_uses_contact_and_describes_everyone(tmp_path) -> None:
    anna = Person("anna", {"Name": "Anna", "Phone_number": "1", "Email": "a@x.ch"})
    ben = Person("ben", {"Name": "Ben", "Occupation": "Nurse"})
    search = SearchProfile(
        "anna_ben", [anna, ben], "anna", {"budget_total": 2400}, tmp_path
    )
    assert search.is_group and search.user_name == "Anna"
    text = search.description_text()
    assert "2 people searching together: Anna, Ben" in text
    assert "## Ben\nName: Ben\nOccupation: Nurse" in text
    assert search.data_dir == tmp_path / "anna_ben"
    with pytest.raises(ProfileError, match="must be one of the members"):
        SearchProfile("x", [anna], "ben", {"budget_total": 1}, tmp_path)
    with pytest.raises(ProfileError, match="budget_total"):
        SearchProfile("x", [anna], "anna", {}, tmp_path)


WGZ_RESULTS = """
<ul><li class="result-row"><h2><a class="result-row__link"
 href="/wg-zimmer/zuerich/8004-zuerich-abc123.html">8004 Zürich</a></h2></li>
<li class="result-row"><h2><a class="result-row__link"
 href="/wg-zimmer/zuerich/8004-zuerich-abc123.html">dup</a></h2></li>
<li><a href="/wgzimmer/search/mate.html?seite=2">2</a></li></ul>
"""
WGZ_LISTING = """
<h1 class="page__title">
<span class="page__title-text">WG-Zimmer in Zürich, CHF 800</span></h1>
<div class="ad-page__rent">Miete pro Monat CHF 800</div>
<dl class="ad-page__facts"><dt>Ab dem</dt><dd>1.1.2027</dd>
<dt>Möbliert</dt><dd>Nein</dd></dl>
<div class="ad-page__texts"><div class="ad-slot"><script>ads()</script></div>
<div class="ad-page__text"><h2>Das Zimmer</h2><p>Hell und ruhig.</p></div></div>
"""


def test_wgzimmer_parsers() -> None:
    paths = parse_results(WGZ_RESULTS)
    assert paths == ["/wg-zimmer/zuerich/8004-zuerich-abc123.html"]
    assert listing_id(paths[0]) == "8004-zuerich-abc123"
    text = parse_listing(WGZ_LISTING)
    assert text.splitlines()[:4] == [
        "WG-Zimmer in Zürich, CHF 800",
        "Miete pro Monat CHF 800",
        "Ab dem: 1.1.2027",
        "Möbliert: Nein",
    ]
    assert "Hell und ruhig." in text and "ads()" not in text
    with pytest.raises(ValueError):
        parse_listing("<html><body>nothing</body></html>")


def test_profile_require_says_where_to_set_each_field(profile) -> None:
    profile.require("gmail_login", "gmail_password")
    with pytest.raises(ProfileError, match="FLATFOX_LOGIN in .env"):
        profile.require("flatfox_login", "gmail_login")
    profile.place = ""
    with pytest.raises(ProfileError, match="fill in place"):
        profile.require("place")


def test_credentials_and_api_keys_come_from_environment(profile) -> None:
    assert profile.gmail_login == "me@gmail.com"
    assert profile.flatfox_login == ""
    assert profile.api_key("deepseek") == "test-key"
    assert profile.api_key("openai") is None


def test_tracker_timestamps_history_and_ids(tmp_path) -> None:
    tracker = Tracker(tmp_path, "site.ch")
    tracker.save("a/b", "drafted", url="https://site.ch/a/b")
    record = tracker.save("a/b", "sent")
    assert tracker.path("a/b").name == "a_b.json"
    assert record["url"] == "https://site.ch/a/b"
    assert [h["status"] for h in record["history"]] == ["drafted", "sent"]
    assert record["created_at"] <= record["updated_at"]
    with pytest.raises(ValueError):
        tracker.save("x", "bogus")


def test_tracker_ignores_working_files(tmp_path) -> None:
    tracker = Tracker(tmp_path, "site.ch")
    tracker.write_working_file("review", {"response": "x"})
    tracker.save("a", "drafted")
    assert [r["id"] for r in tracker.records()] == ["a"]


def test_otp_comes_from_body_not_headers() -> None:
    raw = (
        b"From: noreply@flatfox.ch\r\nMessage-ID: <123456@mail>\r\n"
        b"Content-Type: text/plain\r\n\r\nYour code is 654321."
    )
    body = message_text(email.message_from_bytes(raw))
    assert extract_otp(body) == "654321"
    assert extract_otp("no code here") is None


def test_pick_contact_email() -> None:
    assert pick_contact_email(["https://x.ch", "mailto:", "mailto:a@b.ch"]) == "a@b.ch"
    assert pick_contact_email(["https://x.ch", "mailto:"]) is None
    with pytest.raises(ValueError):
        pick_contact_email(["mailto:a@b.ch", "mailto:c@d.ch"])


def test_deepseek_never_falls_back_to_openai_key(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    with pytest.raises(LLMError, match="No API key for deepseek"):
        create_provider("deepseek", None)


def test_create_provider_defaults_and_unknown() -> None:
    assert create_provider("deepseek", "key").model == DEFAULT_MODELS["deepseek"]
    assert create_provider("openai", "key", "custom").model == "custom"
    assert create_provider("claude", "key").name == "claude"
    with pytest.raises(ValueError):
        create_provider("gemini", "key")


def _chat_completion(content: str) -> SimpleNamespace:
    """
    Build an object shaped like an OpenAI chat completion.

    :param content: Message content.
    :return: The fake completion.
    """
    message = SimpleNamespace(content=content, refusal=None, parsed=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_deepseek_uses_json_mode_and_validates(monkeypatch) -> None:
    provider = create_provider("deepseek", "key")
    sent = {}

    def create(**kwargs):
        sent.update(kwargs)
        return _chat_completion(fit().model_dump_json())

    monkeypatch.setattr(provider.client.chat.completions, "create", create)
    answer = provider.generate("Rate it.", "<listing>x</listing>", FitAssessment)
    assert answer.score == 85
    assert sent["response_format"] == {"type": "json_object"}
    assert "JSON schema" in sent["messages"][0]["content"]

    monkeypatch.setattr(
        provider.client.chat.completions, "create", lambda **_: _chat_completion("")
    )
    with pytest.raises(LLMError, match="empty"):
        provider.generate("Rate it.", "x", FitAssessment)


def test_claude_refusal_raises(monkeypatch) -> None:
    provider = create_provider("claude", "key")
    sent = {}

    def parse(**kwargs):
        sent.update(kwargs)
        return SimpleNamespace(stop_reason="refusal", parsed_output=None)

    monkeypatch.setattr(provider.client.beta.messages, "parse", parse)
    with pytest.raises(LLMError, match="declined"):
        provider.generate("Rate it.", "x", FitAssessment)
    assert sent["fallbacks"] == "default"
    assert sent["output_config"] == {"effort": "medium"}
    assert "temperature" not in sent


@pytest.mark.live
def test_live_llm_roundtrip() -> None:
    """
    One real call per configured provider. Needs API keys in the environment.
    """
    import os

    keys = {"deepseek": "DEEPSEEK_API_KEY", "openai": "OPENAI_API_KEY"}
    keys["claude"] = "ANTHROPIC_API_KEY"
    providers = [name for name, env in keys.items() if os.environ.get(env)]
    if not providers:
        pytest.skip("No provider API key in the environment")
    for name in providers:
        answer = create_provider(name, os.environ[keys[name]]).generate(
            "Rate how well the listing fits a student with a 900 CHF budget.",
            "<listing>Room in Zurich, 850 CHF.</listing>",
            FitAssessment,
        )
        assert 0 <= answer.score <= 100
