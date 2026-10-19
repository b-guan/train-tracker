"""URLs, cache location and defaults."""
import os
from pathlib import Path

# Public GTFS-realtime feeds for NYC Subway (no API key required).
_FEED_BASE = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs"
FEED_URLS = [
    _FEED_BASE,            # 1 2 3 4 5 6 7 S
    _FEED_BASE + "-ace",   # A C E + Rockaway shuttle
    _FEED_BASE + "-bdfm",  # B D F M + Franklin shuttle
    _FEED_BASE + "-g",
    _FEED_BASE + "-jz",
    _FEED_BASE + "-nqrw",
    _FEED_BASE + "-l",
    _FEED_BASE + "-si",    # Staten Island Railway
]

# Service alerts. The JSON flavor carries MTA's alert_type extension, which the protobuf one drops.
ALERTS_URL = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/camsys%2Fsubway-alerts.json"
# Unplanned alert types that don't affect train service, so they get no badge.
INFO_ALERT_TYPES = {"Station Notice", "Boarding Change", "Extra Service", "Special Schedule",
                    "Information Outage"}

STATIC_GTFS_URL ="http://web.mta.info/developers/data/nyct/subway/google_transit.zip"
STATIC_MAX_AGE = 7 * 24 * 3600  # re-download the static schedule weekly

CACHE_DIR = Path(os.environ.get("MTA_TRACKER_CACHE") or Path.home() / ".cache" / "mta_tracker")

HTTP_TIMEOUT = 10
USER_AGENT = "mta-tracker/0.1"

DEFAULT_REFRESH = 30   # seconds between realtime fetches
DEFAULT_ROWS = 4       # trains shown per direction
DEFAULT_WIDTH = 46     # board width in characters
DEFAULT_PAGE_SECONDS = 6  # how long each page of trains stays up before flipping
PAGES = 1             # page 1 = soonest trains, page 2 = the ones after them
