"""
One-time migration from the old ``secret/<name>/`` layout to ``conf/`` + ``data/``.

Usage: ``uv run python -m src.migrate <name>`` (or ``make migrate PROFILE=<name>``).
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

from omegaconf import OmegaConf

from src.personal_profile import CREDENTIAL_ENV, DATA_DIR, PROFILE_DIR

# Old site_credentials.json field -> environment variable that replaces it.
OLD_CREDENTIAL_FIELDS: dict[str, str] = {
    "wohnen_ethz_login": CREDENTIAL_ENV["wohnen_ethz_login"],
    "wohnen_ethz_password": CREDENTIAL_ENV["wohnen_ethz_password"],
    "flatfox_login": CREDENTIAL_ENV["flatfox_login"],
    "flatfox_password": CREDENTIAL_ENV["flatfox_password"],
    "login": CREDENTIAL_ENV["gmail_login"],
    "password": CREDENTIAL_ENV["gmail_password"],
    "login2": CREDENTIAL_ENV["gmail_login2"],
    "password2": CREDENTIAL_ENV["gmail_password2"],
    "DeepSeek_API_KEY": "DEEPSEEK_API_KEY",
    "OpenAI_API_KEY": "OPENAI_API_KEY",
    "Anthropic_API_KEY": "ANTHROPIC_API_KEY",
}


class MigrationError(RuntimeError):
    """
    Raised when migrating would overwrite something or the source is missing.
    """


def migrate(
    name: str,
    secret_dir: Path = Path("secret"),
    profile_dir: Path = PROFILE_DIR,
    data_dir: Path = DATA_DIR,
) -> list[str]:
    """
    Copy an old profile and its listing records into the new layout.

    Writes ``<profile_dir>/<name>.yaml`` from the two JSON files and copies
    ``<secret_dir>/<name>/data/`` to ``<data_dir>/<name>/``. Nothing is deleted and
    nothing is overwritten; credentials are not read or copied.

    :param name: Profile folder name under ``secret_dir``.
    :param secret_dir: Old root folder.
    :param profile_dir: Folder for the new profile config.
    :param data_dir: Root folder for the new listing records.
    :return: Lines describing what was done and what is left to do by hand.
    :raises MigrationError: If the source is missing or a target already exists.
    """
    source = Path(secret_dir) / name
    profile_target = Path(profile_dir) / f"{name}.yaml"
    data_source = source / "data"
    data_target = Path(data_dir) / name
    if not source.is_dir():
        raise MigrationError(f"{source} does not exist")
    if profile_target.exists():
        raise MigrationError(f"{profile_target} already exists; not overwriting it")
    if data_source.is_dir() and data_target.exists():
        raise MigrationError(f"{data_target} already exists; not overwriting it")

    sections = {}
    for key, file_name in (
        ("description", "my_description.json"),
        ("preferences", "living_preferences.json"),
    ):
        path = source / file_name
        if not path.is_file():
            raise MigrationError(f"{path} does not exist")
        sections[key] = json.loads(path.read_text(encoding="utf-8"))

    profile_target.parent.mkdir(parents=True, exist_ok=True)
    OmegaConf.save(OmegaConf.create(sections), profile_target)
    report = [f"Wrote {profile_target}"]

    if data_source.is_dir():
        shutil.copytree(data_source, data_target)
        count = sum(1 for _ in data_target.rglob("*.json"))
        report.append(f"Copied {count} listing records to {data_target}/")

    credentials = source / "site_credentials.json"
    if credentials.is_file():
        # Only the field names are read, never the values.
        fields = json.loads(credentials.read_text(encoding="utf-8")).keys()
        moves = [
            f"  {field} -> {OLD_CREDENTIAL_FIELDS[field]}"
            for field in fields
            if field in OLD_CREDENTIAL_FIELDS
        ]
        report.append(
            f"Copy these values from {credentials} into .env by hand:\n"
            + "\n".join(moves)
        )
    report.append(
        f"Check `uv run python main.py profile={name} command=status`, then delete "
        f"{source}/."
    )
    return report


def main(argv: list[str] | None = None) -> int:
    """
    Run the migration from the command line.

    :param argv: Arguments; defaults to ``sys.argv[1:]``.
    :return: Exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="Profile folder name under secret/")
    args = parser.parse_args(argv)
    try:
        print("\n".join(migrate(args.name)))
    except MigrationError as error:
        print(f"Migration stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
