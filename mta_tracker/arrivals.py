"""Turning realtime feeds into a list of upcoming trains at a station."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from google.transit import gtfs_realtime_pb2


@dataclass(frozen=True)
class Arrival:
    route_id: str
    direction: str    # "N" or "S" (MTA convention: N = uptown / toward the Bronx)
    headsign: str     # name of the trip's final stop
    time: int         # unix epoch seconds
    trip_id: str
    station_id: str   # parent station within the complex

    def minutes_away(self, now: float) -> int:
        return max(0, int((self.time - now) // 60))


def platform_ids(station_ids: Iterable[str]) -> set[str]:
    return {sid + d for sid in station_ids for d in "NS"}


def _parent(stop_id: str) -> str:
    return stop_id[:-1] if stop_id[-1:] in ("N", "S") else stop_id


def get_arrivals(feeds: Iterable[gtfs_realtime_pb2.FeedMessage], station_ids: Iterable[str],
                 station_name: Callable[[str], str], now: float, grace: float = 30
                 ) -> list[Arrival]:
    """Upcoming arrivals at any of `station_ids`, soonest first.

    Trains that left more than `grace` seconds ago and trains terminating at
    this station (not boardable) are left out.
    """
    targets = platform_ids(station_ids)
    arrivals = []
    for feed in feeds:
        for ent in feed.entity:
            if not ent.HasField("trip_update"):
                continue
            tu = ent.trip_update
            updates = tu.stop_time_update
            last = len(updates) - 1
            for i, stu in enumerate(updates):
                if stu.stop_id not in targets:
                    continue
                if i == last:
                    break  # terminates here
                t = stu.arrival.time or stu.departure.time
                if not t or t < now - grace:
                    continue
                arrivals.append(Arrival(
                    route_id=tu.trip.route_id,
                    direction=stu.stop_id[-1],
                    headsign=station_name(_parent(updates[last].stop_id)),
                    time=t,
                    trip_id=tu.trip.trip_id,
                    station_id=_parent(stu.stop_id),
                ))
    arrivals.sort(key=lambda a: (a.time, a.route_id))
    return arrivals
