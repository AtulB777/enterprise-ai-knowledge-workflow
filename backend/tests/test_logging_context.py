import json
import logging

from app.core.logging import JsonFormatter, RequestContextFilter
from app.core.request_context import bind_request_id, bind_user_id, reset_context


def _make_record() -> logging.LogRecord:
    return logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="something happened",
        args=(),
        exc_info=None,
    )


def test_filter_injects_bound_request_id_into_record() -> None:
    reset_context()
    bind_request_id("req-abc")
    record = _make_record()

    RequestContextFilter().filter(record)

    assert record.request_id == "req-abc"  # type: ignore[attr-defined]


def test_filter_does_not_add_fields_when_nothing_bound() -> None:
    reset_context()
    record = _make_record()

    RequestContextFilter().filter(record)

    assert not hasattr(record, "request_id")
    assert not hasattr(record, "user_id")


def test_filter_plus_formatter_produces_correlated_json_log() -> None:
    """End-to-end: bind context, run it through the real filter and real
    formatter, confirm the actual JSON output — not just that the filter
    sets an attribute in isolation.
    """
    reset_context()
    bind_request_id("req-xyz")
    bind_user_id("user-42")
    record = _make_record()
    RequestContextFilter().filter(record)

    output = json.loads(JsonFormatter().format(record))

    assert output["request_id"] == "req-xyz"
    assert output["user_id"] == "user-42"
    assert output["message"] == "something happened"


def test_secret_redaction_still_works_alongside_context_injection() -> None:
    """Regression check: the new auto-injected context fields must not
    interfere with the Phase 2 secret-redaction logic.
    """
    reset_context()
    bind_request_id("req-1")
    record = _make_record()
    record.api_key = "sk-should-never-appear"  # type: ignore[attr-defined]
    RequestContextFilter().filter(record)

    output = json.loads(JsonFormatter().format(record))

    assert "api_key" not in output
    assert output["request_id"] == "req-1"
