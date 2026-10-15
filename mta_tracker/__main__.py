"""CLI: python -m mta_tracker "times sq" """
from __future__ import annotations

import argparse
import logging
import os
import sys
import time

from . import config
from .arrivals import get_arrivals, platform_ids
from .display import AsciiBoard, BoardState
from .feeds import FeedError, FeedPoller
from .stops import Complex, StopIndex, load_index


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="mta_tracker", description="Real-time NYC subway arrival board.")
    p.add_argument("query", nargs="*", help="station name (e.g. 'times sq') or GTFS stop ID (e.g. 127)")
    p.add_argument("-d", "--direction", choices=["N", "S", "both"], default="both",
                   help="N = northbound/uptown, S = southbound/downtown (default: both)")
    p.add_argument("-n", "--rows", type=int, default=config.DEFAULT_ROWS, help="trains shown per direction")
    p.add_argument("-r", "--refresh", type=int, default=config.DEFAULT_REFRESH,
                   help="seconds between data fetches (default: %(default)s)")
    p.add_argument("-w", "--width", type=int, default=config.DEFAULT_WIDTH, help="board width in characters")
    p.add_argument("--once", action="store_true", help="print one board and exit")
    p.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    p.add_argument("--refresh-stations", action="store_true", help="re-download the static station list")
    p.add_argument("-v", "--verbose", action="store_true", help="log fetch details to stderr")
    return p.parse_args(argv)


def describe(index: StopIndex, cx: Complex) -> str:
    names = dict.fromkeys([cx.name] + [index.station_name(sid) for sid in cx.station_ids])
    return f"{' / '.join(names)}  [{' '.join(index.route_labels(cx.routes))}]  (id {cx.id})"


def choose_complex(index: StopIndex, query: str, input_fn=input, out=sys.stdout) -> Complex | None:
    matches = index.search(query)
    if not matches:
        print(f"No station matches {query!r}.", file=out)
        return None
    if len(matches) == 1:
        return matches[0]
    for i, cx in enumerate(matches, 1):
        print(f"{i:>3}. {describe(index, cx)}", file=out)
    while True:
        choice = input_fn(f"Pick a station [1-{len(matches)}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(matches):
            return matches[int(choice) - 1]
        if not choice:
            return None


def run(index: StopIndex, cx: Complex, args: argparse.Namespace) -> None:
    color = not args.no_color and sys.stdout.isatty()
    if color and os.name == "nt":
        os.system("")  # enables ANSI escape processing in the Windows console
    board = AsciiBoard(index.routes, width=args.width, rows=args.rows, color=color,
                       clear=not args.once and sys.stdout.isatty())
    directions = ("N", "S") if args.direction == "both" else (args.direction,)
    poller = FeedPoller(platform_ids(cx.station_ids))

    arrivals, updated_at, error = [], None, None
    next_fetch = 0.0
    try:
        while True:
            if time.time() >= next_fetch:
                try:
                    feeds = poller.poll()
                    updated_at = time.time()
                    arrivals = get_arrivals(feeds, cx.station_ids, index.station_name, updated_at)
                    error = None
                except FeedError as e:
                    error = str(e)
                next_fetch = time.time() + args.refresh

            board.render(BoardState(cx.name, arrivals, time.time(), updated_at, error, directions))
            if args.once:
                break
            time.sleep(1 - time.time() % 1)  # redraw on each second so the clock/ETAs tick
    except KeyboardInterrupt:
        pass
    finally:
        board.close()


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.ERROR,
                        format="%(levelname)s %(name)s: %(message)s")

    if not (config.CACHE_DIR / "index.json").exists() or args.refresh_stations:
        print("Downloading MTA station list (first run only)...", file=sys.stderr)
    try:
        index = load_index(refresh=args.refresh_stations)
    except Exception as e:
        print(f"Could not load station data: {e}", file=sys.stderr)
        return 1

    try:
        query = " ".join(args.query) or input("Station: ")
        cx = choose_complex(index, query)
    except (KeyboardInterrupt, EOFError):
        return 130
    if cx is None:
        return 1

    run(index, cx, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
