import json

from mta_tracker.stops import StopIndex, build_index, load_index, normalize


def test_normalize():
    assert normalize("42nd Street") == "42 st"
    assert normalize("Times Sq-42 St") == "times sq 42 st"
    assert normalize("Flatbush Avenue") == "flatbush av"


def test_routes_per_station_and_express_labels(index):
    assert index.stations["127"].routes == ("1",)
    assert index.stations["626"].routes == ("6", "6X")
    assert index.route_labels(index.stations["626"].routes) == ["6"]
    assert index.routes["6X"].express and index.routes["6X"].label == "6"
    assert index.routes["GS"].label == "S"


def test_transfers_group_complexes(index):
    cx = index.complex_for("A27")
    assert cx.station_ids == ("127", "A27")
    assert cx.name == "Times Sq-42 St"
    assert cx.routes == ("A", "1")
    assert index.complex_for("127") is cx


def test_search_by_name(index):
    assert [c.id for c in index.search("times sq")] == ["127"]
    assert [c.id for c in index.search("port auth")] == ["127"]
    assert [c.id for c in index.search("86 street")] == ["121", "626"]
    assert [c.id for c in index.search("42nd st")] == ["127"]


def test_search_by_id(index):
    assert [c.id for c in index.search("626")] == ["626"]
    assert [c.id for c in index.search("a27n")] == ["127"]


def test_search_fuzzy_and_empty(index):
    assert [c.id for c in index.search("south fery")] == ["142"]
    assert index.search("zzqx") == []
    assert index.search("   ") == []


def test_load_index_uses_fresh_cache(tmp_path, gtfs_zip):
    (tmp_path / "index.json").write_text(json.dumps(build_index(gtfs_zip)))
    idx = load_index(cache_dir=tmp_path)  # must not hit the network
    assert isinstance(idx, StopIndex) and "127" in idx.stations
