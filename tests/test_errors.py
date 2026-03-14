"""Tests for tether._errors — exception hierarchy."""

import pytest

from tether._errors import EOF, ExitStatus, TetherError, Timeout
from tether._types import EOF_TYPE, TIMEOUT_TYPE


class TestTetherError:
    def test_base_exception(self) -> None:
        err = TetherError("something broke")
        assert str(err) == "something broke"
        assert isinstance(err, Exception)

    def test_all_subclasses(self) -> None:
        assert issubclass(Timeout, TetherError)
        assert issubclass(EOF, TetherError)
        assert issubclass(ExitStatus, TetherError)


class TestTimeout:
    def test_default_message(self) -> None:
        err = Timeout("foo.*bar")
        assert err.pattern == "foo.*bar"
        assert "foo.*bar" in str(err)

    def test_custom_message(self) -> None:
        err = Timeout("xyz", msg="custom timeout message")
        assert err.pattern == "xyz"
        assert str(err) == "custom timeout message"

    def test_empty_pattern(self) -> None:
        err = Timeout()
        assert err.pattern == ""

    def test_is_tether_error(self) -> None:
        with pytest.raises(TetherError):
            raise Timeout("test")


class TestEOF:
    def test_default_message(self) -> None:
        err = EOF("buffered content")
        assert err.before == "buffered content"
        assert "EOF" in str(err)

    def test_custom_message(self) -> None:
        err = EOF("data", msg="custom eof")
        assert err.before == "data"
        assert str(err) == "custom eof"

    def test_empty_before(self) -> None:
        err = EOF()
        assert err.before == ""

    def test_is_tether_error(self) -> None:
        with pytest.raises(TetherError):
            raise EOF("test")


class TestExitStatus:
    def test_status_only(self) -> None:
        err = ExitStatus(1)
        assert err.status == 1
        assert err.signal is None
        assert "status 1" in str(err)

    def test_with_signal(self) -> None:
        err = ExitStatus(137, signal=9)
        assert err.status == 137
        assert err.signal == 9
        assert "signal 9" in str(err)

    def test_custom_message(self) -> None:
        err = ExitStatus(2, msg="died")
        assert str(err) == "died"

    def test_is_tether_error(self) -> None:
        with pytest.raises(TetherError):
            raise ExitStatus(1)


class TestSentinels:
    def test_eof_singleton(self) -> None:
        a = EOF_TYPE()
        b = EOF_TYPE()
        assert a is b

    def test_timeout_singleton(self) -> None:
        a = TIMEOUT_TYPE()
        b = TIMEOUT_TYPE()
        assert a is b

    def test_eof_repr(self) -> None:
        assert repr(EOF_TYPE()) == "EOF"

    def test_timeout_repr(self) -> None:
        assert repr(TIMEOUT_TYPE()) == "TIMEOUT"

    def test_isinstance(self) -> None:
        from tether._types import EOF as eof_sentinel
        from tether._types import TIMEOUT as timeout_sentinel

        assert isinstance(eof_sentinel, EOF_TYPE)
        assert isinstance(timeout_sentinel, TIMEOUT_TYPE)

    def test_sentinels_are_distinct_from_exceptions(self) -> None:
        """EOF sentinel and EOF exception are different types."""
        from tether._types import EOF as eof_sentinel

        assert not isinstance(eof_sentinel, EOF)
        assert not isinstance(eof_sentinel, Exception)

    def test_bool(self) -> None:
        assert bool(EOF_TYPE())
        assert bool(TIMEOUT_TYPE())
