"""
Site runners by config name (the file name in ``conf/site/``).
"""

from src.sites.base import Listing, SiteRunner
from src.sites.email_alerts import EmailAlertsRunner
from src.sites.flatfox import FlatfoxRunner
from src.sites.wg_zimmer import WGZimmerRunner
from src.sites.wohnen_ethz import WohnenETHZRunner
from src.sites.woko import WokoRunner

SITES: dict[str, type[SiteRunner]] = {
    "wgzimmer": WGZimmerRunner,
    "flatfox": FlatfoxRunner,
    "woko": WokoRunner,
    "email_alerts": EmailAlertsRunner,
    "wohnen_ethz": WohnenETHZRunner,
}

__all__ = ["SITES", "Listing", "SiteRunner"]
