"""
Command-line interface: ``run`` a site, show ``status``, or ``check-llm``.
"""

import argparse
import os
import sys
from collections import Counter

from src.agent import ApplicationAgent, FitAssessment
from src.lib.logger import logger, setup_logging
from src.lib.tracker import Tracker
from src.llm import DEFAULT_MODELS, PROVIDERS, LLMError, create_provider
from src.personal_profile import PersonalProfile, ProfileError
from src.sites import MODES, SITES

DEFAULT_PROVIDER = os.environ.get("AUTO_HOUSE_PROVIDER", "deepseek")
DEFAULT_PROFILE = os.environ.get("AUTO_HOUSE_PROFILE")


def _add_profile_arg(parser: argparse.ArgumentParser) -> None:
    """
    Add the ``--profile`` option.

    :param parser: Sub-command parser to extend.
    """
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        required=DEFAULT_PROFILE is None,
        help="Folder name under secret/ (default: $AUTO_HOUSE_PROFILE).",
    )


def _add_llm_args(parser: argparse.ArgumentParser) -> None:
    """
    Add the ``--provider`` and ``--model`` options.

    :param parser: Sub-command parser to extend.
    """
    parser.add_argument(
        "--provider",
        choices=PROVIDERS,
        default=DEFAULT_PROVIDER,
        help="LLM provider (default: $AUTO_HOUSE_PROVIDER or deepseek).",
    )
    parser.add_argument(
        "--model",
        help="Model id; defaults per provider: "
        + ", ".join(f"{p}={m}" for p, m in DEFAULT_MODELS.items()),
    )


def build_parser() -> argparse.ArgumentParser:
    """
    Define the command-line arguments.

    :return: The parser.
    """
    parser = argparse.ArgumentParser(
        prog="auto-house",
        description="Find housing listings and draft applications with an LLM agent.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show debug logs.")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="Search a site and handle new listings.")
    _add_profile_arg(run)
    _add_llm_args(run)
    run.add_argument("--site", choices=sorted(SITES), required=True)
    run.add_argument(
        "--mode",
        choices=MODES,
        default="dry-run",
        help="dry-run: draft only (default). confirm: ask before each send. "
        "auto: send drafts that pass review.",
    )
    run.add_argument(
        "--max-sends", type=int, default=5, help="Most messages per run in auto mode."
    )
    run.add_argument(
        "--min-fit", type=int, default=60, help="Lowest fit score (0-100) to apply at."
    )

    status = commands.add_parser("status", help="Show what the agent did per listing.")
    _add_profile_arg(status)
    status.add_argument("--site", choices=sorted(SITES), help="Only this site.")

    check = commands.add_parser("check-llm", help="Make one small call to the LLM.")
    _add_profile_arg(check)
    _add_llm_args(check)
    return parser


def cmd_run(args: argparse.Namespace) -> int:
    """
    Run the agent over one site.

    :param args: Parsed arguments.
    :return: Exit code.
    """
    profile = PersonalProfile(args.profile)
    llm = create_provider(args.provider, profile.api_key(args.provider), args.model)
    agent = ApplicationAgent(profile, llm, min_fit=args.min_fit)
    runner = SITES[args.site](profile, agent, mode=args.mode, max_sends=args.max_sends)
    logger.info(
        "Running %s in %s mode with %s (%s)", args.site, args.mode, llm.name, llm.model
    )
    summary = runner.run()
    print(
        "Summary:",
        ", ".join(f"{k}={v}" for k, v in sorted(summary.items())) or "nothing new",
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """
    Print one line per tracked listing, newest first.

    :param args: Parsed arguments.
    :return: Exit code.
    """
    profile = PersonalProfile(args.profile)
    sites = [args.site] if args.site else sorted(SITES)
    for key in sites:
        tracker = Tracker(profile.data_dir, SITES[key].site)
        records = tracker.records()
        counts = Counter(record["status"] for record in records)
        print(
            f"\n{SITES[key].site}: "
            + (
                ", ".join(f"{s}={n}" for s, n in sorted(counts.items()))
                or "no listings yet"
            )
        )
        for record in records:
            score = (record.get("fit") or {}).get("score", "-")
            when = record.get("updated_at", "legacy")
            where = record.get("url") or record["id"]
            print(f"  {record['status']:<12} fit={score!s:<4} {when:<25} {where}")
    return 0


def cmd_check_llm(args: argparse.Namespace) -> int:
    """
    Make one tiny structured call to check the key and model.

    :param args: Parsed arguments.
    :return: Exit code.
    """
    profile = PersonalProfile(args.profile)
    llm = create_provider(args.provider, profile.api_key(args.provider), args.model)
    answer = llm.generate(
        "Rate how well the listing fits a student with a budget of 900 CHF.",
        "<listing>Room in a shared flat in Zurich, 850 CHF, available now.</listing>",
        FitAssessment,
    )
    print(
        f"{llm.name} ({llm.model}) works: score={answer.score}, {answer.recommendation}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """
    Parse arguments and run the chosen command.

    :param argv: Arguments; defaults to ``sys.argv[1:]``.
    :return: Exit code (0 on success, 1 on a profile or LLM error).
    """
    args = build_parser().parse_args(argv)
    setup_logging(verbose=args.verbose)
    commands = {"run": cmd_run, "status": cmd_status, "check-llm": cmd_check_llm}
    try:
        return commands[args.command](args)
    except (ProfileError, LLMError) as error:
        logger.error("%s", error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
