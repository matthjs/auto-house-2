"""
Entry point. Run ``uv run python main.py --help`` for usage.
"""

import sys

from src.cli import main

if __name__ == "__main__":
    sys.exit(main())
