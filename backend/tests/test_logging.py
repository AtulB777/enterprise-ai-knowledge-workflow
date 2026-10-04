import json
import logging

from app.core.logging import JsonFormatter


def _make_record(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="a log message",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_produces_valid_json_with_core_fields() -> None:
    formatter = JsonFormatter()
    record = _make_record(request_id="abc-123")

    output = json.loads(formatter.format(record))

    assert output["message"] == "a log message"
    assert output["level"] == "INFO"
    assert output["request_id"] == "abc-123"


def test_json_formatter_redacts_sensitive_extra_fields() -> None:
    formatter = JsonFormatter()
    record = _make_record(password="hunter2", api_key="sk-secret", user_id="u-1")

    output = json.loads(formatter.format(record))

    assert "password" not in output
    assert "api_key" not in output
    assert output["user_id"] == "u-1"
