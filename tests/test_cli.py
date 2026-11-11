"""
Tests for the Hydra config, the entry point and the migration from ``secret/``.
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


def load_config(*overrides: str) -> DictConfig:
    """
    Compose the real config from ``conf/`` with test overrides.

    :param overrides: Hydra overrides, for example ``"site=flatfox"``.
    :return: The composed config.
    """
    with initialize_config_dir(config_dir=CONF_DIR, version_base="1.3"):
        return compose(
            config_name="config",
            overrides=["profile=example", "profile_name=tester", *overrides],
        )


def test_config_groups_match_code() -> None:
    conf = Path(CONF_DIR)
    assert {p.stem for p in (conf / "site").glob("*.yaml")} == set(SITES)
    for path in (conf / "llm").glob("*.yaml"):
        cfg = load_config(f"llm={path.stem}")
        assert cfg.llm.provider == path.stem
        assert cfg.llm.model == DEFAULT_MODELS[path.stem]


def test_defaults_are_safe() -> None:
    cfg = load_config()
    assert cfg.mode == "dry-run"
    assert cfg.command == "run"
    assert cfg.get("site") is None


def test_status_runs_from_config(tmp_path, monkeypatch, capsys) -> None:
    isolate_env(monkeypatch)
    cfg = load_config(
        "command=status",
        f"data_dir={tmp_path}",
        "+profile.preferences.budget_upper_bound=900",
    )
    assert run_command(cfg) == 0
    assert "flatfox.ch: no listings yet" in capsys.readouterr().out
    assert build_profile(cfg).data_dir == tmp_path / "tester"


def test_errors_exit_nonzero() -> None:
    assert run_command(load_config("+profile.preferences.budget_upper_bound=900")) == 1
    assert run_command(load_config("command=bogus")) == 1
    no_budget = load_config("site=flatfox")
    assert run_command(no_budget) == 1


def test_env_defaults_fill_only_missing_groups(monkeypatch) -> None:
    isolate_env(monkeypatch)
    monkeypatch.setenv("AUTO_HOUSE_PROFILE", "me")
    monkeypatch.setenv("AUTO_HOUSE_LLM", "claude")
    assert main.apply_env_defaults(["site=flatfox"]) == [
        "site=flatfox",
        "profile=me",
        "llm=claude",
    ]
    assert main.apply_env_defaults(["llm=openai"]) == ["llm=openai", "profile=me"]


def test_migrate_copies_profile_and_records(tmp_path) -> None:
    old = tmp_path / "secret" / "me"
    (old / "data" / "flatfox.ch").mkdir(parents=True)
    (old / "my_description.json").write_text(json.dumps({"Name": "Me"}))
    (old / "living_preferences.json").write_text(
        json.dumps({"budget_upper_bound": "900", "place": "Zurich"})
    )
    (old / "data" / "flatfox.ch" / "abc.json").write_text(json.dumps({"id": "abc"}))
    (old / "site_credentials.json").write_text(json.dumps({"login": "do-not-leak"}))

    report = migrate(
        "me",
        secret_dir=tmp_path / "secret",
        profile_dir=tmp_path / "conf",
        data_dir=tmp_path / "data",
    )

    assert (tmp_path / "data" / "me" / "flatfox.ch" / "abc.json").is_file()
    assert (old / "data" / "flatfox.ch" / "abc.json").is_file()
    assert "login -> GMAIL_ADDRESS" in "\n".join(report)
    assert "do-not-leak" not in "\n".join(report)

    with initialize_config_dir(config_dir=str(tmp_path / "conf"), version_base="1.3"):
        profile = compose(config_name="me")
    assert profile.preferences.place == "Zurich"

    with pytest.raises(MigrationError, match="already exists"):
        migrate(
            "me",
            secret_dir=tmp_path / "secret",
            profile_dir=tmp_path / "conf",
            data_dir=tmp_path / "data",
        )
