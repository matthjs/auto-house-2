"""
Tests for the Hydra config, the commands, the entry point and the migration.
"""

import json
from pathlib import Path

import pytest
from hydra import compose, initialize_config_dir
from omegaconf import DictConfig

import main
from src.cli import build_profile, run_command
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
        "site=flatfox",
        "search=anna_ben",
        "llm=claude",
    ]
    assert main.apply_env_defaults(["llm=openai"]) == ["llm=openai", "search=anna_ben"]
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
