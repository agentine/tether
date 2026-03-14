"""Tests for _screen.py: ANSI escape sequence handling."""

from __future__ import annotations

from tether._screen import has_ansi, strip_ansi


class TestStripAnsi:
    def test_basic_color(self) -> None:
        assert strip_ansi("\x1b[31mhello\x1b[0m") == "hello"

    def test_bold(self) -> None:
        assert strip_ansi("\x1b[1mhello\x1b[0m") == "hello"

    def test_no_ansi(self) -> None:
        assert strip_ansi("hello") == "hello"

    def test_empty(self) -> None:
        assert strip_ansi("") == ""

    def test_multiple_sequences(self) -> None:
        text = "\x1b[1m\x1b[31mbold red\x1b[0m"
        assert strip_ansi(text) == "bold red"

    def test_bracketed_paste_mode(self) -> None:
        assert strip_ansi("\x1b[?2004h") == ""
        assert strip_ansi("\x1b[?2004l") == ""

    def test_cursor_movement(self) -> None:
        assert strip_ansi("\x1b[2J\x1b[H") == ""

    def test_osc_title(self) -> None:
        assert strip_ansi("\x1b]0;my title\x07hello") == "hello"

    def test_mixed_text_and_ansi(self) -> None:
        text = "before\x1b[31m red \x1b[0mafter"
        assert strip_ansi(text) == "before red after"


class TestHasAnsi:
    def test_with_ansi(self) -> None:
        assert has_ansi("\x1b[31mhello\x1b[0m") is True

    def test_without_ansi(self) -> None:
        assert has_ansi("hello") is False

    def test_empty(self) -> None:
        assert has_ansi("") is False
