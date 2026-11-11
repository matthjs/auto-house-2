"""
Run a command from a composed Hydra config: ``run``, ``status`` or ``check-llm``.
"""

from collections import Counter
from pathlib import Path

from omegaconf import DictConfig, OmegaConf

from src.agent import ApplicationAgent, FitAssessment
from src.lib.logger import logger, setup_logging
from src.lib.tracker import Tracker
from src.llm import LLMError, LLMProvider, create_provider
from src.personal_profile import PersonalProfile, ProfileError
from src.sites import MODES, SITES

COMMANDS = ("run", "status", "check-llm")


class ConfigError(ValueError):
    """
    Raised when the config asks for something that does not exist.
    """


def build_profile(cfg: DictConfig) -> PersonalProfile:
    """
    Create the profile selected in the config.

    :param cfg: Composed config with ``profile``, ``profile_name`` and ``data_dir``.
    :return: The profile, with credentials read from the environment.
    """
    profile_cfg = OmegaConf.to_container(cfg.profile, resolve=True)
    return PersonalProfile(
        name=cfg.profile_name,
        description=profile_cfg.get("description") or {},
        preferences=profile_cfg.get("preferences") or {},
        data_root=Path(cfg.data_dir),
    )


def build_llm(cfg: DictConfig, profile: PersonalProfile) -> LLMProvider:
    """
    Create the LLM provider selected in the config.

    :param cfg: Composed config with ``llm.provider`` and ``llm.model``.
    :param profile: Profile, used to look up the API key.
    :return: The provider.
    :raises ConfigError: If the provider is unknown.
    """
    provider = cfg.llm.provider
    try:
        return create_provider(provider, profile.api_key(provider), cfg.llm.model)
    except ValueError as error:
        raise ConfigError(str(error)) from error


def cmd_run(cfg: DictConfig) -> int:
    """
    Run the agent over the selected site.

    :param cfg: Composed config.
    :return: Exit code.
    :raises ConfigError: If no site or an unknown mode is chosen.
    """
    if cfg.get("site") is None:
        raise ConfigError(f"Choose a site: site={'|'.join(SITES)}")
    if cfg.mode not in MODES:
        raise ConfigError(f"Unknown mode '{cfg.mode}'. Choose from: {', '.join(MODES)}")
    profile = build_profile(cfg)
    llm = build_llm(cfg, profile)
    agent = ApplicationAgent(profile, llm, min_fit=cfg.min_fit)
    runner = SITES[cfg.site.name](
        profile, agent, mode=cfg.mode, max_sends=cfg.max_sends
    )
    logger.info(
        "Running %s in %s mode with %s (%s)",
        cfg.site.name,
        cfg.mode,
        llm.name,
        llm.model,
    )
    summary = runner.run()
    counts = ", ".join(f"{k}={v}" for k, v in sorted(summary.items()))
    print("Summary:", counts or "nothing new")
    return 0


def cmd_status(cfg: DictConfig) -> int:
    """
    Print one line per tracked listing, newest first, for every site.

    :param cfg: Composed config.
    :return: Exit code.
    """
    profile = build_profile(cfg)
    for runner in SITES.values():
        records = Tracker(profile.data_dir, runner.site).records()
        counts = Counter(record["status"] for record in records)
        totals = ", ".join(f"{s}={n}" for s, n in sorted(counts.items()))
        print(f"\n{runner.site}: {totals or 'no listings yet'}")
        for record in records:
            score = (record.get("fit") or {}).get("score", "-")
            when = record.get("updated_at", "legacy")
            where = record.get("url") or record["id"]
            print(f"  {record['status']:<12} fit={score!s:<4} {when:<25} {where}")
    return 0


def cmd_check_llm(cfg: DictConfig) -> int:
    """
    Make one tiny structured call to check the API key and model.

    :param cfg: Composed config.
    :return: Exit code.
    """
    llm = build_llm(cfg, build_profile(cfg))
    answer = llm.generate(
        "Rate how well the listing fits a student with a budget of 900 CHF.",
        "<listing>Room in a shared flat in Zurich, 850 CHF, available now.</listing>",
        FitAssessment,
    )
    print(
        f"{llm.name} ({llm.model}) works: score={answer.score}, {answer.recommendation}"
    )
    return 0


def run_command(cfg: DictConfig) -> int:
    """
    Set up logging and run the command named in ``cfg.command``.

    :param cfg: Composed config.
    :return: Exit code (0 on success, 1 on a config, profile or LLM error).
    """
    setup_logging(verbose=cfg.verbose)
    commands = {"run": cmd_run, "status": cmd_status, "check-llm": cmd_check_llm}
    try:
        if cfg.command not in commands:
            raise ConfigError(
                f"Unknown command '{cfg.command}'. Choose from: {', '.join(COMMANDS)}"
            )
        return commands[cfg.command](cfg)
    except (ConfigError, ProfileError, LLMError) as error:
        logger.error("%s", error)
        return 1
