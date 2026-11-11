"""
Run a command from a composed Hydra config.

Commands: ``search``, ``show``, ``mark``, ``send``, ``run`` (batch), ``status`` and
``check-llm``. Everything that would contact someone or change a decision obeys
``dry_run`` (on by default).
"""

import json
from collections import Counter
from pathlib import Path
from typing import Any

from omegaconf import DictConfig, OmegaConf

from src.agent import ApplicationAgent, FitAssessment
from src.lib.commute import CommuteClient, Place
from src.lib.email_client import EmailError
from src.lib.errors import SendError
from src.lib.logger import logger, setup_logging
from src.lib.tracker import Tracker
from src.llm import LLMError, LLMProvider, create_provider
from src.search_profile import Person, ProfileError, SearchProfile
from src.sites import SITES, Listing, SiteRunner

COMMANDS = ("search", "show", "mark", "send", "run", "status", "check-llm")
DECISIONS = ("sent", "rejected", "skipped", "drafted")


class ConfigError(ValueError):
    """
    Raised when the config asks for something that does not exist.
    """


def _container(node: Any) -> Any:
    """
    Convert an OmegaConf node to plain Python, or pass plain values through.

    :param node: Config node or value.
    :return: Plain dicts, lists and values.
    """
    if OmegaConf.is_config(node):
        return OmegaConf.to_container(node, resolve=True)
    return node


def load_person(name: str, person_dir: Path) -> Person:
    """
    Load one person's file.

    :param name: File name without ``.yaml``.
    :param person_dir: Folder with person files.
    :return: The person.
    :raises ProfileError: If the file does not exist.
    """
    path = Path(person_dir) / f"{name}.yaml"
    if not path.is_file():
        raise ProfileError(f"Missing {path}. Create it with the setup skill.")
    data = _container(OmegaConf.load(path)) or {}
    return Person(name=name, description=data.get("description") or {})


def build_profile(cfg: DictConfig) -> SearchProfile:
    """
    Create the search selected in the config, with its members' files.

    :param cfg: Composed config with ``search``, ``search_name``, ``person_dir`` and
        ``data_dir``.
    :return: The search, with credentials read from the environment.
    """
    search = _container(cfg.search)
    members = [
        load_person(name, cfg.person_dir) for name in search.get("members") or []
    ]
    places = [
        Place(
            name=str(place["name"]),
            address=str(place["address"]),
            who=[str(name) for name in place.get("who") or []],
        )
        for place in search.get("places") or []
    ]
    return SearchProfile(
        name=cfg.search_name,
        members=members,
        contact=search.get("contact") or (members[0].name if members else ""),
        preferences=search.get("preferences") or {},
        data_root=Path(cfg.data_dir),
        places=places,
    )


def build_llm(cfg: DictConfig, profile: SearchProfile) -> LLMProvider:
    """
    Create the LLM provider selected in the config.

    :param cfg: Composed config with ``llm.provider`` and ``llm.model``.
    :param profile: Search, used to look up the API key.
    :return: The provider.
    :raises ConfigError: If the provider is unknown.
    """
    provider = cfg.llm.provider
    try:
        return create_provider(provider, profile.api_key(provider), cfg.llm.model)
    except ValueError as error:
        raise ConfigError(str(error)) from error


def build_runner(
    cfg: DictConfig, profile: SearchProfile, agent: ApplicationAgent | None = None
) -> SiteRunner:
    """
    Create the runner for the selected site.

    :param cfg: Composed config.
    :param profile: The search.
    :param agent: Agent for batch mode.
    :return: The runner.
    :raises ConfigError: If no site is selected.
    """
    if cfg.get("site") is None:
        raise ConfigError(f"Choose a site: site={'|'.join(SITES)}")
    commute = cfg.get("commute") or {}
    client = None
    if commute.get("enabled", True) and profile.places:
        client = CommuteClient(departure=str(commute.get("departure", "08:00")))
    return SITES[cfg.site.name](
        profile,
        agent,
        dry_run=bool(cfg.dry_run),
        max_sends=cfg.max_sends,
        options=_container(cfg.site),
        commute=client,
    )


def read_message_file(path: str) -> tuple[str, str]:
    """
    Read a message written for a listing.

    The first line may be ``Subject: ...``; the rest is the body.

    :param path: File path.
    :return: Subject (empty if none) and body.
    :raises ConfigError: If the file is missing or the body is empty.
    """
    file = Path(path)
    if not file.is_file():
        raise ConfigError(f"message_file {path} does not exist")
    lines = file.read_text(encoding="utf-8").strip().splitlines()
    subject = ""
    if lines and lines[0].lower().startswith("subject:"):
        subject = lines.pop(0).split(":", 1)[1].strip()
    body = "\n".join(lines).strip()
    if not body:
        raise ConfigError(f"message_file {path} has no message body")
    return subject, body


def _listing_record(
    cfg: DictConfig, profile: SearchProfile
) -> tuple[SiteRunner, dict[str, Any]]:
    """
    Find the record of ``listing`` on the selected site.

    :param cfg: Composed config with ``site`` and ``listing``.
    :param profile: The search.
    :return: The site's runner and the listing's record.
    :raises ConfigError: If no listing is given or it has no record.
    """
    runner = build_runner(cfg, profile)
    if not cfg.get("listing"):
        raise ConfigError("Choose a listing: listing=<id> (see command=status)")
    record = runner.tracker.get(str(cfg.listing))
    if record is None:
        raise ConfigError(f"No record of listing {cfg.listing} on {runner.site}")
    return runner, record


def cmd_search(cfg: DictConfig) -> int:
    """
    Search a site and print its open listings as JSON (stdout).

    Listings are saved as ``found``; nobody is contacted.

    :param cfg: Composed config.
    :return: Exit code.
    """
    runner = build_runner(cfg, build_profile(cfg))
    print(json.dumps(runner.collect(), ensure_ascii=False, indent=2))
    return 0


def cmd_show(cfg: DictConfig) -> int:
    """
    Print one listing's record as JSON.

    :param cfg: Composed config.
    :return: Exit code.
    """
    _, record = _listing_record(cfg, build_profile(cfg))
    record = {key: value for key, value in record.items() if key != "history"}
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


def cmd_mark(cfg: DictConfig) -> int:
    """
    Record a decision for a listing, optionally with the message that was used.

    :param cfg: Composed config with ``listing``, ``decision`` and optionally
        ``message_file``.
    :return: Exit code.
    :raises ConfigError: If the decision is unknown.
    """
    runner, record = _listing_record(cfg, build_profile(cfg))
    if cfg.get("decision") not in DECISIONS:
        raise ConfigError(f"Choose a decision: decision={'|'.join(DECISIONS)}")
    fields: dict[str, Any] = {}
    if cfg.get("message_file"):
        fields["subject"], fields["response"] = read_message_file(cfg.message_file)
    if cfg.get("note"):
        fields["note"] = str(cfg.note)
    if cfg.dry_run:
        print(
            f"[dry run] Would mark {record['id']} on {runner.site} as {cfg.decision}"
            f" (now {record['status']}). Add dry_run=false to save."
        )
        return 0
    runner.tracker.save(record["id"], str(cfg.decision), **fields)
    print(f"Marked {record['id']} on {runner.site} as {cfg.decision}.")
    return 0


def cmd_send(cfg: DictConfig) -> int:
    """
    Email an approved message to the landlord of a listing (email sites only).

    :param cfg: Composed config with ``listing`` and ``message_file``.
    :return: Exit code.
    :raises ConfigError: If the site has no email contact, the listing has no
        address, or no message file is given.
    """
    profile = build_profile(cfg)
    runner, record = _listing_record(cfg, profile)
    if not runner.needs_contact_email:
        raise ConfigError(
            f"{runner.site} is contacted on the website: send the message there, then "
            f"use command=mark decision=sent"
        )
    if not record.get("contact_email"):
        raise ConfigError(f"Listing {record['id']} has no contact email")
    if not cfg.get("message_file"):
        raise ConfigError("Give the approved message: message_file=<path>")
    subject, body = read_message_file(cfg.message_file)
    if cfg.dry_run:
        print(
            f"[dry run] Would email {record['contact_email']}\nSubject: {subject}\n\n"
            f"{body}\n\nAdd dry_run=false to send."
        )
        return 0
    profile.require(*runner.send_fields())
    listing = Listing(
        id=record["id"],
        url=record.get("url", ""),
        content="",
        contact_email=record["contact_email"],
    )
    try:
        runner.send(listing, subject, body)
    except (SendError, EmailError) as error:
        runner.tracker.save(record["id"], "failed", error=str(error))
        raise ConfigError(f"Sending failed: {error}") from error
    runner.tracker.save(record["id"], "sent", subject=subject, response=body)
    print(f"Sent to {record['contact_email']} and marked {record['id']} as sent.")
    return 0


def cmd_run(cfg: DictConfig) -> int:
    """
    Batch mode: the built-in LLM agent evaluates and drafts every open listing.

    :param cfg: Composed config.
    :return: Exit code.
    """
    profile = build_profile(cfg)
    llm = build_llm(cfg, profile)
    agent = ApplicationAgent(profile, llm, min_fit=cfg.min_fit)
    runner = build_runner(cfg, profile, agent)
    logger.info(
        "Batch run on %s with %s (%s), dry_run=%s",
        runner.site,
        llm.name,
        llm.model,
        cfg.dry_run,
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
            where = record.get("url") or ""
            print(f"  {record['status']:<12} fit={score!s:<4} {record['id']}  {where}")
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
    commands = {
        "search": cmd_search,
        "show": cmd_show,
        "mark": cmd_mark,
        "send": cmd_send,
        "run": cmd_run,
        "status": cmd_status,
        "check-llm": cmd_check_llm,
    }
    try:
        if cfg.command not in commands:
            raise ConfigError(
                f"Unknown command '{cfg.command}'. Choose from: {', '.join(COMMANDS)}"
            )
        return commands[cfg.command](cfg)
    except (ConfigError, ProfileError, LLMError) as error:
        logger.error("%s", error)
        return 1
