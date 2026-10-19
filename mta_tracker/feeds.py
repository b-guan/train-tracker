"""Fetching and parsing the MTA GTFS-realtime subway feeds."""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable

import requests
from google.transit import gtfs_realtime_pb2

from . import config

log = logging.getLogger(__name__)


class FeedError(Exception):
    """Raised when no feed could be fetched at all."""


def fetch_feed(url: str, session: requests.Session, timeout: float = config.HTTP_TIMEOUT
               ) -> gtfs_realtime_pb2.FeedMessage:
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(resp.content)
    return feed


def feed_mentions(feed: gtfs_realtime_pb2.FeedMessage, stop_ids: set[str]) -> bool:
    return any(
        stu.stop_id in stop_ids
        for ent in feed.entity if ent.HasField("trip_update")
        for stu in ent.trip_update.stop_time_update
    )


def alerted_routes(feed: dict, now: float) -> frozenset[str]:
    """Route IDs with an unplanned service alert in effect now (delays, suspensions, reroutes...).

    `feed` is the parsed JSON alerts feed. Planned work comes as "lmm:planned_work:*"
    entities and is skipped, as are notices that don't affect service.
    """
    routes = set()
    for ent in feed.get("entity", []):
        if ":planned_work:" in ent.get("id", ""):
            continue
        alert = ent.get("alert", {})
        if alert.get("transit_realtime.mercury_alert", {}).get("alert_type") in config.INFO_ALERT_TYPES:
            continue
        periods = alert.get("active_period") or [{}]  # no period = always in effect
        if not any(p.get("start", 0) <= now < (p.get("end") or float("inf")) for p in periods):
            continue
        routes.update(e["route_id"] for e in alert.get("informed_entity", []) if e.get("route_id"))
    return frozenset(routes)


def fetch_alerted_routes(session: requests.Session, now: float, url: str = config.ALERTS_URL,
                         timeout: float = config.HTTP_TIMEOUT) -> frozenset[str]:
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    return alerted_routes(resp.json(), now)


class FeedPoller:
    """Polls the realtime feeds for a set of platform stop IDs (e.g. {"127N", "127S"}).

    The first poll fetches every feed; afterwards only the feeds that actually
    served those stops are fetched, with a full re-scan every `rescan_interval`
    seconds to pick up rerouted service.
    """

    def __init__(self, stop_ids: Iterable[str], urls: list[str] | None = None,
                 rescan_interval: float = 600, session: requests.Session | None = None):
        self.stop_ids = set(stop_ids)
        self.urls = list(urls or config.FEED_URLS)
        self.rescan_interval = rescan_interval
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", config.USER_AGENT)
        self._relevant: list[str] = []
        self._last_scan: float | None = None

    def _needs_full_scan(self) -> bool:
        return (not self._relevant or self._last_scan is None
                or time.monotonic() - self._last_scan > self.rescan_interval)

    def poll(self) -> list[gtfs_realtime_pb2.FeedMessage]:
        full = self._needs_full_scan()
        urls = self.urls if full else self._relevant

        results: dict[str, gtfs_realtime_pb2.FeedMessage] = {}
        errors: list[str] = []
        with ThreadPoolExecutor(max_workers=len(urls)) as pool:
            futures = {pool.submit(fetch_feed, url, self.session): url for url in urls}
            for fut in as_completed(futures):
                url = futures[fut]
                try:
                    results[url] = fut.result()
                except Exception as e:  # network, HTTP or protobuf errors: skip this feed
                    log.warning("Feed %s failed: %s", url, e)
                    errors.append(f"{url.rsplit('%2F', 1)[-1]}: {e}")

        if not results:
            raise FeedError("all feeds failed: " + "; ".join(errors))

        if full:
            # Keep feeds that served our stops, plus any that failed so they are retried.
            self._relevant = [u for u in urls
                              if u not in results or feed_mentions(results[u], self.stop_ids)]
            self._last_scan = time.monotonic()

        return [results[u] for u in urls if u in results]
