from mta_tracker import __main__ as cli
from mta_tracker import terminal as keys
from mta_tracker.picker import StationPicker, pick_station


class FakeTerminal:
    """Replays scripted keys; None entries simulate a read timeout."""

    def __init__(self, script):
        self.script = list(script)
        self.output = []
        self.stream = self

    def write(self, text):
        self.output.append(text)

    def flush(self):
        pass

    def read_key(self, timeout=None):
        if not self.script:
            raise AssertionError("ran out of scripted keys")
        return self.script.pop(0)


def type_text(text):
    return list(text)


def test_fuzzy_search_ranking(index):
    assert [c.id for c in index.search("tmes sq")] == ["127"]       # subsequence
    assert [c.id for c in index.search("south fery")] == ["142"]    # typo
    assert [c.id for c in index.search("86 st 6")] == ["626"]       # trailing word names a line
    assert [c.id for c in index.search("86 st")] == ["121", "626"]
    assert index.search("van cortlandt")[0].id == "101"


def test_empty_query_lists_every_station_alphabetically(index):
    picker = StationPicker(index, color=False)
    names = [c.name for c in picker.results]
    assert names == sorted(names) and len(names) == len(index.complexes)


def test_typing_filters_and_arrows_select(index):
    picker = StationPicker(index, color=False)
    for k in "86 st":
        assert picker.handle_key(k) is None
    assert [c.id for c in picker.results] == ["121", "626"]
    picker.handle_key(keys.DOWN)
    picker.handle_key(keys.DOWN)  # clamps at the last result
    assert picker.current.id == "626"
    picker.handle_key(keys.UP)
    assert picker.handle_key(keys.ENTER) == ("select", index.complex_for("121"))


def test_editing_keys(index):
    picker = StationPicker(index, "times sq", color=False)
    picker.handle_key(keys.BACKSPACE)
    assert picker.query == "times s"
    picker.handle_key(keys.CTRL_W)
    assert picker.query == "times "
    picker.handle_key(keys.CTRL_U)
    assert picker.query == "" and len(picker.results) == len(index.complexes)
    for k in "zzqx":
        picker.handle_key(k)
    assert picker.results == [] and picker.handle_key(keys.ENTER) is None
    assert picker.handle_key(keys.ESC) == ("cancel", None)


def test_render_keeps_selection_visible(index):
    picker = StationPicker(index, color=False)
    picker.handle_key(keys.END)
    lines = picker.lines(width=60, height=8)  # room for only 3 results
    assert len(lines) == 8
    assert any(line.startswith(" > ") and "Van Cortlandt" in line for line in lines)
    assert "Up/Down move" in lines[-1]


def test_pick_station_loop(index):
    term = FakeTerminal(type_text("port") + [None, keys.ENTER])
    cx, query = pick_station(index, term, color=False)
    assert cx.id == "127" and query == "port"
    assert "42 St-Port Authority" in "".join(term.output)


def test_interactive_search_board_search_quit(index, monkeypatch):
    """Full flow: search -> board -> 's' back to search (query kept) -> Esc quits."""
    monkeypatch.setattr("mta_tracker.feeds.FeedPoller.poll", lambda self: [])
    term = FakeTerminal(type_text("south") + [keys.ENTER, None, "s", keys.ESC])
    picks = []
    real_pick = cli.pick_station

    def recording_pick(index, term, query, color):
        picks.append(query)
        return real_pick(index, term, query, color=False)

    monkeypatch.setattr(cli, "pick_station", recording_pick)
    monkeypatch.setattr(cli.keys, "RawTerminal", lambda: _ContextFor(term))
    args = cli.parse_args(["--rows", "2", "--no-color", "--no-animation"])
    assert cli.interactive(index, args) == 0
    assert picks == ["", "south"]
    screens = "".join(term.output)
    assert "SOUTH FERRY" in screens and "[s]earch [q]uit" in screens


class _ContextFor:
    def __init__(self, term):
        self.term = term

    def __enter__(self):
        return self.term

    def __exit__(self, *exc):
        return False
