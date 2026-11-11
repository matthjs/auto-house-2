"""
Site runners by config name (the file name in ``conf/site/``).
"""

from src.sites.base import Listing, SiteRunner
from src.sites.flatfox import FlatfoxRunner
from src.sites.wg_zimmer import WGZimmerRunner
from src.sites.wohnen_ethz import WohnenETHZRunner

SITES: dict[str, type[SiteRunner]] = {
    "wgzimmer": WGZimmerRunner,
    "flatfox": FlatfoxRunner,
    "wohnen_ethz": WohnenETHZRunner,
}

__all__ = ["SITES", "Listing", "SiteRunner"]
