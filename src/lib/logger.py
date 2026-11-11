"""
Project logger. Call :func:`setup_logging` once at startup.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

logger = logging.getLogger("auto_house")


def setup_logging(log_dir: Path = Path("out"), verbose: bool = False) -> None:
    """
    Log to the console and to a rotating file.

    :param log_dir: Folder for ``app.log`` (5 files of 5 MB at most).
    :param verbose: Show debug messages on the console too.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    file_handler = RotatingFileHandler(
        log_dir / "app.log", maxBytes=5 * 1024 * 1024, backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    for handler in (file_handler, console_handler):
        handler.setFormatter(formatter)

    logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.setLevel(logging.DEBUG)
