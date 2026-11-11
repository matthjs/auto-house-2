"""
Site runners by command-line name.
"""

from src.sites.base import MODES, Listing, Mode, SiteRunner
from src.sites.flatfox import FlatfoxRunner
from src.sites.wg_zimmer import WGZimmerRunner
from src.sites.wohnen_ethz import WohnenETHZRunner

SITES: dict[str, type[SiteRunner]] = {
    "wgzimmer": WGZimmerRunner,
    "flatfox": FlatfoxRunner,
    "wohnen-ethz": WohnenETHZRunner,
}

__all__ = ["MODES", "SITES", "Listing", "Mode", "SiteRunner"]
