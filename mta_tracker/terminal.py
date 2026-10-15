"""Minimal cross-platform raw keyboard input (Windows console and POSIX ttys), no dependencies."""
from __future__ import annotations

import os
import sys
import time

UP, DOWN, LEFT, RIGHT = "UP", "DOWN", "LEFT", "RIGHT"
PGUP, PGDN, HOME, END = "PGUP", "PGDN", "HOME", "END"
ENTER, ESC, BACKSPACE, TAB, DELETE = "ENTER", "ESC", "BACKSPACE", "TAB", "DELETE"
CTRL_C, CTRL_U, CTRL_W = "CTRL_C", "CTRL_U", "CTRL_W"

_CONTROL = {"\r": ENTER, "\n": ENTER, "\x1b": ESC, "\x08": BACKSPACE, "\x7f": BACKSPACE,
            "\t": TAB, "\x03": CTRL_C, "\x15": CTRL_U, "\x17": CTRL_W}

ALT_SCREEN_ON, ALT_SCREEN_OFF = "\x1b[?1049h", "\x1b[?1049l"
HIDE_CURSOR, SHOW_CURSOR = "\x1b[?25l", "\x1b[?25h"


class RawTerminal:
    """Context manager putting the terminal in unbuffered, no-echo mode on the alternate screen.

    `read_key(timeout)` returns a printable character, one of the key constants
    above, or None if nothing was pressed within `timeout` seconds.
    """

    def __init__(self, stream=None):
        self.stream = stream or sys.stdout
        self._saved = None

    def __enter__(self) -> "RawTerminal":
        if os.name == "nt":
            os.system("")  # enable ANSI escape processing in the Windows console
        else:
            import termios
            fd = sys.stdin.fileno()
            self._saved = termios.tcgetattr(fd)
            mode = termios.tcgetattr(fd)
            mode[0] &= ~(termios.IXON | termios.ICRNL)                   # iflag
            mode[3] &= ~(termios.ICANON | termios.ECHO | termios.ISIG)  # lflag
            mode[6][termios.VMIN], mode[6][termios.VTIME] = 1, 0
            termios.tcsetattr(fd, termios.TCSADRAIN, mode)
        self.stream.write(ALT_SCREEN_ON + HIDE_CURSOR)
        self.stream.flush()
        return self

    def __exit__(self, *exc) -> None:
        self.stream.write(SHOW_CURSOR + ALT_SCREEN_OFF)
        self.stream.flush()
        if self._saved is not None:
            import termios
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._saved)

    def write(self, text: str) -> None:
        self.stream.write(text)
        self.stream.flush()

    def read_key(self, timeout: float | None = None) -> str | None:
        return _read_key_windows(timeout) if os.name == "nt" else _read_key_posix(timeout)


# --- Windows -----------------------------------------------------------------

_WIN_SPECIAL = {"H": UP, "P": DOWN, "K": LEFT, "M": RIGHT, "I": PGUP, "Q": PGDN,
                "G": HOME, "O": END, "S": DELETE}


def _read_key_windows(timeout: float | None) -> str | None:
    import msvcrt
    deadline = None if timeout is None else time.monotonic() + timeout
    while not msvcrt.kbhit():
        if deadline is not None and time.monotonic() >= deadline:
            return None
        time.sleep(0.01)
    ch = msvcrt.getwch()
    if ch in ("\x00", "\xe0"):  # arrow/function keys arrive as a two-part code
        return _WIN_SPECIAL.get(msvcrt.getwch())
    return _CONTROL.get(ch, ch)


# --- POSIX -------------------------------------------------------------------

_CSI = {"A": UP, "B": DOWN, "C": RIGHT, "D": LEFT, "H": HOME, "F": END,
        "5~": PGUP, "6~": PGDN, "1~": HOME, "4~": END, "7~": HOME, "8~": END, "3~": DELETE}


def _read_key_posix(timeout: float | None) -> str | None:
    import codecs
    import select

    fd = sys.stdin.fileno()

    def ready(t):
        return bool(select.select([fd], [], [], t)[0])

    if not ready(timeout):
        return None
    first = os.read(fd, 1)
    if first == b"\x1b":
        if not ready(0.05):
            return ESC
        intro = os.read(fd, 1)
        if intro not in (b"[", b"O"):
            return ESC
        seq = b""
        while ready(0.05):
            b = os.read(fd, 1)
            seq += b
            if 0x40 <= b[0] <= 0x7E:  # final byte of the escape sequence
                break
        return _CSI.get(seq.decode("ascii", "replace"))

    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    ch = decoder.decode(first)
    while not ch and ready(0.05):
        ch = decoder.decode(os.read(fd, 1))
    return _CONTROL.get(ch, ch) if ch else None
