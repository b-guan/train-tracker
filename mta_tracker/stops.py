"""Static GTFS: station names, station complexes, and the routes serving each station.

The static schedule zip is ~6 MB and parsing stop_times.txt takes a few seconds,
so the result is condensed into a small JSON index that is cached on disk.
"""
from __future__ import annotations

import csv
import difflib
import io
import json
import logging
import re
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import requests

from . import config

log = logging.getLogger(__name__)

INDEX_VERSION = 1


@dataclass(frozen=True)
class Route:
    id: str
    label: str        # what riders see, e.g. "S" for GS/FS/H, "6" for 6X
    express: bool
    color: str        # hex, no leading '#'
    text_color: str
    sort: int


@dataclass(frozen=True)
class Station:
    id: str           # parent station id, e.g. "127"; platforms are "127N"/"127S"
    name: str
    lat: float
    lon: float
    routes: tuple[str, ...]


@dataclass(frozen=True)
class Complex:
    """Stations linked by in-system transfers, e.g. Times Sq-42 St (127, 725, 902, A27, R16)."""
    id: str
    name: str
    station_ids: tuple[str, ...]
    routes: tuple[str, ...]


# --- building the index -----------------------------------------------------

def _read_csv(zf: zipfile.ZipFile, name: str):
    with zf.open(name) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))


def build_index(zip_path: Path) -> dict:
    """Condense a static GTFS zip into the JSON-serialisable index used by StopIndex."""
    with zipfile.ZipFile(zip_path) as zf:
        stations: dict[str, dict] = {}
        parent_of: dict[str, str] = {}
        for row in _read_csv(zf, "stops.txt"):
            if row.get("location_type") == "1":
                stations[row["stop_id"]] = {
                    "name": row["stop_name"],
                    "lat": float(row["stop_lat"]),
                    "lon": float(row["stop_lon"]),
                    "routes": set(),
                }
            elif row.get("parent_station"):
                parent_of[row["stop_id"]] = row["parent_station"]

        routes = {}
        for i, row in enumerate(_read_csv(zf, "routes.txt")):
            rid = row["route_id"]
            short = row.get("route_short_name") or rid
            express = len(short) > 1 and short.endswith("X")
            routes[rid] = {
                "label": short[:-1] if express else short,
                "express": express,
                "color": row.get("route_color") or "808080",
                "text_color": row.get("route_text_color") or "FFFFFF",
                "sort": int(row.get("route_sort_order") or i),
            }

        route_of_trip = {row["trip_id"]: row["route_id"] for row in _read_csv(zf, "trips.txt")}
        for row in _read_csv(zf, "stop_times.txt"):
            route = route_of_trip.get(row["trip_id"])
            station = stations.get(parent_of.get(row["stop_id"], row["stop_id"]))
            if route and station is not None:
                station["routes"].add(route)

        # Union-find over transfers.txt to group stations into complexes.
        root = {sid: sid for sid in stations}

        def find(x: str) -> str:
            while root[x] != x:
                root[x] = root[root[x]]
                x = root[x]
            return x

        if "transfers.txt" in zf.namelist():
            for row in _read_csv(zf, "transfers.txt"):
                a, b = row["from_stop_id"], row["to_stop_id"]
                if a in root and b in root:
                    root[find(a)] = find(b)

    groups: dict[str, list[str]] = {}
    for sid in sorted(stations):
        groups.setdefault(find(sid), []).append(sid)

    for st in stations.values():
        st["routes"] = sorted(st["routes"], key=lambda r: routes.get(r, {}).get("sort", 999))

    return {
        "version": INDEX_VERSION,
        "built_at": time.time(),
        "routes": routes,
        "stations": stations,
        "complexes": list(groups.values()),
    }


def _download(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=config.HTTP_TIMEOUT,
                      headers={"User-Agent": config.USER_AGENT}) as resp:
        resp.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(1 << 16):
                f.write(chunk)
    tmp.replace(dest)


def load_index(cache_dir: Path | None = None, max_age: float = config.STATIC_MAX_AGE,
               refresh: bool = False) -> "StopIndex":
    """Load the cached index, rebuilding it from a fresh static GTFS download when stale."""
    cache_dir = Path(cache_dir or config.CACHE_DIR)
    index_path = cache_dir / "index.json"

    cached = None
    if index_path.exists():
        try:
            cached = json.loads(index_path.read_text(encoding="utf-8"))
            if cached.get("version") != INDEX_VERSION:
                cached = None
        except (OSError, ValueError):
            cached = None

    if cached and not refresh and time.time() - cached.get("built_at", 0) < max_age:
        return StopIndex(cached)

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        zip_path = cache_dir / "google_transit.zip"
        log.info("Downloading static GTFS from %s", config.STATIC_GTFS_URL)
        _download(config.STATIC_GTFS_URL, zip_path)
        data = build_index(zip_path)
        index_path.write_text(json.dumps(data), encoding="utf-8")
        zip_path.unlink(missing_ok=True)
        return StopIndex(data)
    except (requests.RequestException, OSError, zipfile.BadZipFile, KeyError) as e:
        if cached:
            log.warning("Could not refresh static GTFS (%s); using cached copy", e)
            return StopIndex(cached)
        raise


# --- searching --------------------------------------------------------------

_ABBREVIATIONS = {
    "street": "st", "avenue": "av", "ave": "av", "square": "sq", "boulevard": "blvd",
    "road": "rd", "parkway": "pkwy", "place": "pl", "plaza": "plz", "heights": "hts",
    "junction": "jct", "center": "ctr", "centre": "ctr", "terminal": "term",
}


def normalize(text: str) -> str:
    text = text.lower().replace("&", " and ")
    text = re.sub(r"\b(\d+)(st|nd|rd|th)\b", r"\1", text)  # 42nd -> 42
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(_ABBREVIATIONS.get(t, t) for t in text.split())


class StopIndex:
    def __init__(self, data: dict):
        self.routes = {rid: Route(rid, **r) for rid, r in data["routes"].items()}
        self.stations = {
            sid: Station(sid, s["name"], s["lat"], s["lon"], tuple(s["routes"]))
            for sid, s in data["stations"].items()
        }
        self.complexes: list[Complex] = []
        self._complex_of: dict[str, Complex] = {}
        for ids in data["complexes"]:
            names = [self.stations[i].name for i in ids]
            # Most common member name wins (Times Sq-42 St over 42 St-Port Authority).
            name = max(dict.fromkeys(names), key=names.count)
            routes = {r for i in ids for r in self.stations[i].routes}
            cx = Complex(ids[0], name, tuple(ids), tuple(sorted(routes, key=self.route_sort_key)))
            self.complexes.append(cx)
            for i in ids:
                self._complex_of[i] = cx

    def route_sort_key(self, route_id: str):
        r = self.routes.get(route_id)
        return (r.sort if r else 999, route_id)

    def route_labels(self, route_ids) -> list[str]:
        """Rider-facing labels with duplicates (6/6X, GS/FS/H) collapsed, in sort order."""
        labels = [self.routes[r].label if r in self.routes else r for r in route_ids]
        return list(dict.fromkeys(labels))

    def station_name(self, station_id: str) -> str:
        st = self.stations.get(station_id)
        return st.name if st else station_id

    def complex_for(self, station_id: str) -> Complex | None:
        return self._complex_of.get(station_id)

    def search(self, query: str, limit: int = 20) -> list[Complex]:
        """Find complexes by station ID (e.g. "127", "127N") or by (partial) name."""
        raw = query.strip().upper()
        for candidate in (raw, raw[:-1] if raw[-1:] in ("N", "S") else None):
            if candidate and candidate in self._complex_of:
                return [self._complex_of[candidate]]

        q = normalize(query)
        q_tokens = q.split()
        if not q_tokens:
            return []

        scores: dict[str, tuple[int, Complex]] = {}

        def consider(cx: Complex, score: int) -> None:
            if cx.id not in scores or score < scores[cx.id][0]:
                scores[cx.id] = (score, cx)

        def token_matches(qt: str, tokens: list[str]) -> bool:
            # Numbers must match exactly ("1" shouldn't hit "103 St"); words may be prefixes.
            return qt in tokens if qt.isdigit() else any(t.startswith(qt) for t in tokens)

        for st in self.stations.values():
            name = normalize(st.name)
            tokens = name.split()
            if all(token_matches(qt, tokens) for qt in q_tokens):
                score = 0 if name == q else 1 if all(qt in tokens for qt in q_tokens) else 2
                consider(self._complex_of[st.id], score)

        if not scores:
            by_name: dict[str, list[Station]] = {}
            for st in self.stations.values():
                by_name.setdefault(normalize(st.name), []).append(st)
            for match in difflib.get_close_matches(q, list(by_name), n=limit, cutoff=0.6):
                for st in by_name[match]:
                    consider(self._complex_of[st.id], 3)

        ranked = sorted(scores.values(), key=lambda sc: (sc[0], sc[1].name, sc[1].id))
        return [cx for _, cx in ranked[:limit]]
