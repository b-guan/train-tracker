from mta_tracker.display import BoardState
from mta_tracker.feeds import alerted_routes, fetch_alerted_routes

NOW = 1_800_000_000


def alert(ent_id, routes, alert_type="Delays", periods=((NOW - 60, NOW + 600),)):
    return {"id": ent_id, "alert": {
        "active_period": [{"start": s, "end": e} for s, e in periods],
        "informed_entity": [{"agency_id": "MTASBWY", "route_id": r} for r in routes],
        "transit_realtime.mercury_alert": {"alert_type": alert_type},
    }}


def test_alerted_routes_keeps_unplanned_service_alerts_in_effect():
    feed = {"entity": [
        alert("lmm:alert:1", ["J", "Z"]),
        alert("lmm:alert:2", ["4"], "Part Suspended"),
        alert("lmm:planned_work:3", ["A"], "Planned - Stops Skipped"),  # planned work
        alert("lmm:alert:4", ["E"], "Station Notice"),                  # doesn't affect trains
        alert("lmm:alert:5", ["G"], periods=((NOW - 600, NOW - 60),)),  # already over
        alert("lmm:alert:6", ["L"], periods=()),                         # no period: always on
        {"id": "lmm:alert:7", "alert": {"informed_entity": [{"stop_id": "F12"}]}},  # no route
    ]}
    assert alerted_routes(feed, NOW) == {"J", "Z", "4", "L"}
    assert alerted_routes({}, NOW) == frozenset()


def test_open_ended_period_stays_in_effect():
    feed = {"entity": [alert("lmm:alert:1", ["7"], periods=((NOW - 60, None),))]}
    assert alerted_routes(feed, NOW) == {"7"}


def test_fetch_alerted_routes_reads_the_json_feed():
    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"entity": [alert("lmm:alert:1", ["Q"])]}

    class Session:
        def get(self, url, timeout):
            self.url = url
            return Resp()

    session = Session()
    assert fetch_alerted_routes(session, NOW) == {"Q"}
    assert session.url.endswith("subway-alerts.json")


def test_board_state_matches_express_variants_to_the_alerted_line():
    state = BoardState("x", [], NOW, alerted_routes=frozenset({"6", "GS"}))
    assert state.has_alert("6") and state.has_alert("6X") and state.has_alert("GS")
    assert not state.has_alert("7X") and not state.has_alert("FS")
