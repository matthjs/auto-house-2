"""
Tests for the Hydra config, the commands, the entry point and the migration.
"""

import json
from pathlib import Path

import pytest
from hydra import compose, initialize_config_dir
from omegaconf import DictConfig

import main
from src.cli import build_profile, build_runner, run_command
from src.lib.commute import CommuteClient, Place
from src.lib.email_client import EmailClient
from src.lib.tracker import Tracker
from src.llm import DEFAULT_MODELS
from src.migrate import MigrationError, migrate
from src.sites import SITES
from tests.conftest import isolate_env

CONF_DIR = str(Path(__file__).resolve().parent.parent / "conf")


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Create two people and a group search in a temporary folder, with no real
    credentials in the environment.

    :param tmp_path: Pytest's temporary directory.
    :param monkeypatch: Pytest's monkeypatch.
    :return: The folder.
    """
    isolate_env(monkeypatch)
    people = tmp_path / "person"
    people.mkdir()
    (people / "anna.yaml").write_text("description:\n  Name: Anna\n  Email: a@x.ch\n")
    (people / "ben.yaml").write_text("description:\n  Name: Ben\n")
    return tmp_path


def load_config(workspace: Path, *overrides: str) -> DictConfig:
    """
    Compose the real config from ``conf/`` with a group search from ``workspace``.

    :param workspace: Folder from the ``workspace`` fixture.
    :param overrides: Extra Hydra overrides.
    :return: The composed config.
    """
    with initialize_config_dir(config_dir=CONF_DIR, version_base="1.3"):
        return compose(
            config_name="config",
            overrides=[
                "search=example",
                "search_name=anna_ben",
                "search.members=[anna,ben]",
                "search.contact=anna",
                "search.preferences.budget_total=2400",
                f"person_dir={workspace / 'person'}",
                f"data_dir={workspace / 'data'}",
                *overrides,
            ],
        )


def save_record(workspace: Path, site: str, record: dict) -> None:
    """
    Write a listing record as the tracker would.

    :param workspace: Folder from the ``workspace`` fixture.
    :param site: Site folder name.
    :param record: Record content with ``id``.
    """
    folder = workspace / "data" / "anna_ben" / site
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{record['id']}.json").write_text(json.dumps(record))


def test_config_groups_match_code(workspace) -> None:
    conf = Path(CONF_DIR)
    assert {p.stem for p in (conf / "site").glob("*.yaml")} == set(SITES)
    for path in (conf / "llm").glob("*.yaml"):
        cfg = load_config(workspace, f"llm={path.stem}")
        assert cfg.llm.provider == path.stem
        assert cfg.llm.model == DEFAULT_MODELS[path.stem]


def test_defaults_are_safe(workspace) -> None:
    cfg = load_config(workspace)
    assert cfg.dry_run is True
    assert cfg.command == "status"
    assert cfg.get("site") is None


def test_group_search_loads_people(workspace) -> None:
    search = build_profile(load_config(workspace))
    assert [p.display_name for p in search.members] == ["Anna", "Ben"]
    assert search.user_email == "a@x.ch"
    assert search.data_dir == workspace / "data" / "anna_ben"


def test_status_runs(workspace, capsys) -> None:
    assert run_command(load_config(workspace, "command=status")) == 0
    assert "flatfox.ch: no listings yet" in capsys.readouterr().out


def test_mark_is_dry_run_by_default(workspace, capsys) -> None:
    save_record(workspace, "wgzimmer.ch", {"id": "x1", "status": "found"})
    args = ("command=mark", "site=wgzimmer", "listing=x1", "decision=sent")
    assert run_command(load_config(workspace, *args)) == 0
    assert "[dry run]" in capsys.readouterr().out
    record_path = workspace / "data" / "anna_ben" / "wgzimmer.ch" / "x1.json"
    assert json.loads(record_path.read_text())["status"] == "found"

    message = workspace / "msg.txt"
    message.write_text("Subject: Room\n\nHello!")
    args += (f"message_file={message}", "dry_run=false")
    assert run_command(load_config(workspace, *args)) == 0
    saved = json.loads(record_path.read_text())
    assert saved["status"] == "sent" and saved["subject"] == "Room"
    assert saved["response"] == "Hello!"


def test_send_refuses_form_sites_and_dry_runs_email(workspace, capsys) -> None:
    save_record(workspace, "wgzimmer.ch", {"id": "x1", "status": "found"})
    message = workspace / "msg.txt"
    message.write_text("Subject: Room\nHello!")
    form = ("command=send", "site=wgzimmer", "listing=x1", f"message_file={message}")
    assert run_command(load_config(workspace, *form)) == 1

    save_record(
        workspace,
        "wohnen.ethz.ch",
        {"id": "e1", "status": "found", "contact_email": "landlord@x.ch"},
    )
    email = (
        "command=send",
        "site=wohnen_ethz",
        "listing=e1",
        f"message_file={message}",
    )
    assert run_command(load_config(workspace, *email)) == 0
    out = capsys.readouterr().out
    assert "[dry run] Would email landlord@x.ch" in out and "Hello!" in out


def test_errors_exit_nonzero(workspace) -> None:
    assert run_command(load_config(workspace, "command=run")) == 1
    assert run_command(load_config(workspace, "command=bogus")) == 1
    missing = ("command=show", "site=flatfox", "listing=nope")
    assert run_command(load_config(workspace, *missing)) == 1


def test_env_defaults_and_llm_auto_pick(monkeypatch) -> None:
    isolate_env(monkeypatch)
    monkeypatch.setenv("AUTO_HOUSE_SEARCH", "anna_ben")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert main.apply_env_defaults(["site=flatfox"]) == [
        "search=anna_ben",
        "llm=claude",
        "site=flatfox",
    ]
    assert main.apply_env_defaults(["llm=openai"]) == ["search=anna_ben", "llm=openai"]
    assert main.apply_env_defaults(["--cfg", "job"])[-2:] == ["--cfg", "job"]
    monkeypatch.setenv("AUTO_HOUSE_LLM", "deepseek")
    assert main.apply_env_defaults([])[-1] == "llm=deepseek"


def test_migrate_makes_one_person_search(tmp_path) -> None:
    old = tmp_path / "secret" / "me"
    (old / "data" / "flatfox.ch").mkdir(parents=True)
    (old / "my_description.json").write_text(json.dumps({"Name": "Me"}))
    (old / "living_preferences.json").write_text(
        json.dumps({"budget_upper_bound": "900", "place": "Zurich"})
    )
    (old / "data" / "flatfox.ch" / "abc.json").write_text(json.dumps({"id": "abc"}))
    (old / "site_credentials.json").write_text(json.dumps({"login": "do-not-leak"}))
    dirs = {
        "secret_dir": tmp_path / "secret",
        "person_dir": tmp_path / "person",
        "search_dir": tmp_path / "search",
        "data_dir": tmp_path / "data",
    }

    report = "\n".join(migrate("me", **dirs))

    assert (tmp_path / "data" / "me" / "flatfox.ch" / "abc.json").is_file()
    assert (old / "data" / "flatfox.ch" / "abc.json").is_file()
    assert "login -> GMAIL_ADDRESS" in report and "do-not-leak" not in report
    with initialize_config_dir(config_dir=str(tmp_path / "search"), version_base="1.3"):
        search = compose(config_name="me")
    assert search.members == ["me"] and search.contact == "me"
    assert search.preferences.budget_total == "900"
    with pytest.raises(MigrationError, match="already exists"):
        migrate("me", **dirs)


def test_places_from_config_turn_on_commute(workspace) -> None:
    place = "{name:ETH,address:'Rämistrasse 101, 8092 Zürich',who:[ben]}"
    cfg = load_config(workspace, f"search.places=[{place}]", "site=flatfox")
    profile = build_profile(cfg)
    assert profile.places == [
        Place(name="ETH", address="Rämistrasse 101, 8092 Zürich", who=["ben"])
    ]
    assert isinstance(build_runner(cfg, profile).commute, CommuteClient)
    off = load_config(
        workspace, f"search.places=[{place}]", "site=flatfox", "commute.enabled=false"
    )
    assert build_runner(off, build_profile(off)).commute is None
    no_places = load_config(workspace, "site=flatfox")
    assert build_runner(no_places, build_profile(no_places)).commute is None


def save_draft(workspace: Path, listing_id: str, score: int, status="drafted") -> None:
    """
    Store a batch-mode draft on Flatfox for the ``anna_ben`` search.

    :param workspace: Folder from the ``workspace`` fixture.
    :param listing_id: Listing id.
    :param score: Fit score.
    :param status: Record status.
    """
    tracker = Tracker(workspace / "data" / "anna_ben", "flatfox.ch")
    tracker.save(
        listing_id,
        status,
        url=f"https://flatfox.ch/{listing_id}/",
        text="Rooms: 3.5\nRent per month (CHF): 2400\nA bright flat.",
        commute="Commute by public transport:\n- ETH: 15 min (Ben)",
        fit={"score": score, "reasons": ["Near ETH"], "red_flags": []},
        subject="Wohnung",
        response="Guten Tag, wir interessieren uns für die Wohnung.",
        review_issues=["Too short"] if status == "needs_review" else [],
    )


def test_digest_is_printed_until_enabled(workspace, capsys) -> None:
    save_draft(workspace, "1", 85)
    assert run_command(load_config(workspace, "command=digest")) == 0
    out = capsys.readouterr().out
    assert "[digest off] Would email a@x.ch" in out
    assert "Rent per month (CHF): 2400" in out and "ETH: 15 min (Ben)" in out
    assert "Guten Tag" in out
    tracker = Tracker(workspace / "data" / "anna_ben", "flatfox.ch")
    assert "notified_at" not in tracker.get("1")


def test_digest_emails_members_once(workspace, capsys, monkeypatch) -> None:
    save_draft(workspace, "1", 85)
    save_draft(workspace, "2", 70, status="needs_review")
    save_draft(workspace, "3", 40)
    save_draft(workspace, "4", 90, status="skipped")
    monkeypatch.setenv("GMAIL_ADDRESS", "anna@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    sent = []

    def fake_send(self, recipients, subject, content, bcc_self) -> None:
        sent.append((recipients, subject, content, bcc_self))

    monkeypatch.setattr(EmailClient, "_send", fake_send)
    cfg = load_config(
        workspace, "command=digest", "digest.enabled=true", "digest.note='Test run'"
    )
    assert run_command(cfg) == 0
    [(to, subject, body, bcc)] = sent
    assert body.startswith("Test run\n")
    assert to == ["a@x.ch"] and not bcc
    assert subject == "auto-house: 2 new listings"
    assert body.index("Fit 85") < body.index("Fit 70")
    assert "needs a check before sending: Too short" in body
    assert "flatfox.ch/3/" not in body and "flatfox.ch/4/" not in body

    capsys.readouterr()
    assert run_command(cfg) == 0
    assert len(sent) == 1
    assert "Nothing new" in capsys.readouterr().out


def test_digest_needs_gmail_to_send(workspace) -> None:
    save_draft(workspace, "1", 85)
    cfg = load_config(workspace, "command=digest", "digest.enabled=true")
    assert run_command(cfg) == 1


def test_digest_lists_shortlisted_without_a_draft(workspace, capsys) -> None:
    tracker = Tracker(workspace / "data" / "anna_ben", "flatfox.ch")
    tracker.save(
        "7",
        "shortlisted",
        url="https://flatfox.ch/7/",
        text="Rooms: 3\nRent per month (CHF): 2100",
        fit={"score": 75, "reasons": ["Cheap"], "red_flags": []},
    )
    assert run_command(load_config(workspace, "command=digest")) == 0
    out = capsys.readouterr().out
    assert "Fit 75/100" in out and "Rent per month (CHF): 2100" in out
    assert "Subject: Wohnung" not in out and "  Subject:" not in out


def test_batch_mode_only_judges_by_default(workspace) -> None:
    assert load_config(workspace).batch_drafts is False
