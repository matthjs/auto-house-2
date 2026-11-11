"""
Entry point. Examples:

    uv run python main.py profile=<you> site=flatfox                 # dry run
    uv run python main.py profile=<you> site=flatfox mode=confirm llm=claude
    uv run python main.py profile=<you> command=status
    uv run python main.py site=flatfox --cfg job                     # show config

Settings live in ``conf/``; passwords and API keys in ``.env``.
"""

import os
import sys

import hydra
from dotenv import load_dotenv
from omegaconf import DictConfig

from src.cli import run_command

# Environment variable -> config group it picks a default for.
ENV_DEFAULTS = {"AUTO_HOUSE_PROFILE": "profile", "AUTO_HOUSE_LLM": "llm"}


def apply_env_defaults(argv: list[str]) -> list[str]:
    """
    Add ``group=value`` overrides for groups set in the environment but not in argv.

    Hydra's defaults list cannot read environment variables, so this lets
    ``AUTO_HOUSE_PROFILE`` and ``AUTO_HOUSE_LLM`` in ``.env`` act as defaults.

    :param argv: Command-line arguments without the program name.
    :return: The arguments with the extra overrides appended.
    """
    extra = []
    for env_var, group in ENV_DEFAULTS.items():
        value = os.environ.get(env_var)
        given = any(arg.lstrip("+~").startswith(f"{group}=") for arg in argv)
        if value and not given:
            extra.append(f"{group}={value}")
    return argv + extra


# Hydra does not pass the task's return value back, so the exit code is kept here.
exit_code = 0


@hydra.main(config_path="conf", config_name="config", version_base="1.3")
def main(cfg: DictConfig) -> None:
    """
    Run the command chosen in the config and remember its exit code.

    :param cfg: Config composed by Hydra.
    """
    global exit_code
    exit_code = run_command(cfg)


if __name__ == "__main__":
    # Variables already set in the shell win over .env.
    load_dotenv(".env", override=False)
    sys.argv = [sys.argv[0], *apply_env_defaults(sys.argv[1:])]
    main()
    sys.exit(exit_code)
