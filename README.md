# MTA Tracker

A real-time NYC subway arrival board. Enter a station and see which trains are coming and how many minutes away they are. For now it renders as an ASCII board in the terminal. An LED matrix display is planned.

```
+--------------------------------------------+
| TIMES SQ-42 ST                 12:23:20 AM |
+--------------------------------------------+
| NORTHBOUND                                 |
| (E) Jamaica Center-Parsons/Archer    2 min |
| (2) Wakefield-241 St                 3 min |
| (1) Van Cortlandt Park-242 St        3 min |
| (3) Harlem-148 St                    4 min |
| SOUTHBOUND                                 |
| (Q) Coney Island-Stillwell Av        1 min |
| (A) Far Rockaway-Mott Av             5 min |
| (N) Coney Island-Stillwell Av        8 min |
| (1) South Ferry                      9 min |
+--------------------------------------------+
| Updated 12:23:20 AM                        |
+--------------------------------------------+
```

## Setup

```sh
python -m venv .venv
.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` elsewhere
pip install -r requirements.txt
```

No API key is needed. The MTA's subway GTFS-realtime feeds are public.

## Usage

```sh
python -m mta_tracker "times sq"           # live board, Ctrl+C to quit
python -m mta_tracker 86 st                # ambiguous -> pick from a list
python -m mta_tracker 127                  # GTFS station ID (127N/127S also work)
python -m mta_tracker union sq -d S -n 6   # southbound only, 6 trains
python -m mta_tracker "1 av" --once        # print one board and exit
```

| Option | Meaning |
| --- | --- |
| `-d N\|S\|both` | Direction. N is northbound/uptown and S is southbound/downtown, by MTA convention. |
| `-n ROWS` | Trains shown per direction (default 4) |
| `-r SECONDS` | Seconds between data fetches (default 30). The board redraws every second. |
| `-w WIDTH` | Board width in characters |
| `--once` | Render one frame and exit |
| `--no-color` | Plain ASCII, no ANSI route colors |
| `--refresh-stations` | Re-download the static station list |

On first run, the static GTFS schedule (about 6 MB) is downloaded and condensed into `~/.cache/mta_tracker/index.json`. Set `MTA_TRACKER_CACHE` to put it somewhere else. The index is refreshed weekly.

## How it works

- `stops.py` builds the index from the static GTFS. It holds station names, which routes stop at each station (from `stop_times.txt`), and station **complexes**. A complex is a set of stations joined by `transfers.txt`. For example, Times Sq-42 St is five GTFS stations: 127, 725, 902, A27, and R16.
- `feeds.py` fetches the 8 realtime feeds in parallel. After the first poll, it fetches only the feeds that serve the chosen station, and does a full re-scan every 10 minutes.
- `arrivals.py` turns the feeds into a sorted list of `Arrival` objects. Trains that terminate at the station are skipped. The headsign is the name of the trip's last stop.
- `display/` holds the renderers. Each one takes a renderer-agnostic `BoardState`, and `AsciiBoard` draws it at a fixed size.

## LED display (next step)

Add `mta_tracker/display/led.py` with a class that has `render(state: BoardState)` and `close()`. On a Raspberry Pi this would use [rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix). Then construct that class in `__main__.run()` in place of `AsciiBoard`. Route colors are available as `index.routes[route_id].color`.

## Tests

```sh
python -m pytest
```
