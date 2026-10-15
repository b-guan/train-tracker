import io

from google.transit import gtfs_realtime_pb2

from mta_tracker.arrivals import get_arrivals, platform_ids
from mta_tracker.display import AsciiBoard, BoardState
from mta_tracker.feeds import FeedPoller, feed_mentions

NOW = 1_800_000_000


def make_feed(trips):
    """trips: list of (trip_id, route_id, [(stop_id, time), ...])"""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "1.0"
    for trip_id, route_id, stops in trips:
        ent = feed.entity.add(id=trip_id)
        ent.trip_update.trip.trip_id = trip_id
        ent.trip_update.trip.route_id = route_id
        for stop_id, t in stops:
            stu = ent.trip_update.stop_time_update.add(stop_id=stop_id)
            stu.arrival.time = t
            stu.departure.time = t
    feed.entity.add(id="empty").trip_update.trip.trip_id = "no-updates"
    return feed


FEED = make_feed([
    ("down1", "1", [("101S", NOW - 600), ("127S", NOW + 300), ("142S", NOW + 1200)]),
    ("down2", "1", [("127S", NOW + 60), ("142S", NOW + 900)]),
    ("up1", "1", [("142N", NOW - 60), ("127N", NOW + 120), ("101N", NOW + 1800)]),
    ("gone", "1", [("127S", NOW - 120), ("142S", NOW + 600)]),
    ("term", "1", [("121N", NOW + 30), ("127N", NOW + 200)]),  # terminates at 127
    ("ace", "A", [("A27S", NOW + 30), ("A55S", NOW + 3000)]),
])


def test_get_arrivals(index):
    arrivals = get_arrivals([FEED], ("127", "A27"), index.station_name, NOW)
    assert [a.trip_id for a in arrivals] == ["ace", "down2", "up1", "down1"]
    by_trip = {a.trip_id: a for a in arrivals}
    assert by_trip["down1"].direction == "S" and by_trip["down1"].headsign == "South Ferry"
    assert by_trip["up1"].direction == "N" and by_trip["up1"].headsign == "Van Cortlandt Park-242 St"
    assert by_trip["ace"].headsign == "A55"  # unknown stop falls back to its ID
    assert by_trip["down1"].minutes_away(NOW) == 5


def test_feed_mentions():
    assert feed_mentions(FEED, platform_ids(["127"]))
    assert not feed_mentions(FEED, platform_ids(["999"]))


def test_poller_narrows_to_relevant_feeds(monkeypatch):
    other = make_feed([("x", "L", [("L06N", NOW)])])
    feeds = {"u1": FEED, "u2": other}
    fetched = []

    def fake_fetch(url, session, timeout=10):
        fetched.append(url)
        return feeds[url]

    monkeypatch.setattr("mta_tracker.feeds.fetch_feed", fake_fetch)
    poller = FeedPoller(platform_ids(["127"]), urls=["u1", "u2"])
    assert len(poller.poll()) == 2
    fetched.clear()
    assert poller.poll() == [FEED]
    assert fetched == ["u1"]


def test_ascii_board_layout(index):
    arrivals = get_arrivals([FEED], ("127", "A27"), index.station_name, NOW)
    board = AsciiBoard(index.routes, width=40, rows=3, color=False, clear=False, stream=io.StringIO())
    lines = board.format(BoardState("Times Sq-42 St", arrivals, NOW, updated_at=NOW))
    assert len({len(line) for line in lines}) == 1 and len(lines[0]) == 40
    text = "\n".join(lines)
    assert "TIMES SQ-42 ST" in text and "NORTHBOUND" in text and "SOUTHBOUND" in text
    assert "(1) Van Cortlandt Park-242 St" in text
    assert "(A) A55" in text and "Now" in text and "5 min" in text
    # fixed height regardless of how many trains there are
    empty = board.format(BoardState("X", [], NOW, updated_at=NOW))
    assert len(empty) == len(lines) and "No trains scheduled" in "\n".join(empty)


def test_ascii_board_stale_status(index):
    board = AsciiBoard(index.routes, color=False, clear=False, stream=io.StringIO())
    lines = board.format(BoardState("X", [], NOW, updated_at=NOW - 90, error="timeout"))
    assert "STALE 90s old: timeout" in "\n".join(lines)
