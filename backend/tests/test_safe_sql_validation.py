"""Layers 1-3 of ADR-012 decision 3's four-layer defense: statement shape,
keyword blocklist, table allowlist. Layer 4 (DB-enforced read-only
transaction) is tested separately in test_safe_sql_tool.py against real
Postgres.
"""

import pytest

from app.services.agents.tools.safe_sql_validation import SafeSqlError, validate_safe_sql


def test_accepts_simple_select_star() -> None:
    result = validate_safe_sql("SELECT * FROM agent_document_overview")
    assert result == "SELECT * FROM agent_document_overview"


def test_accepts_select_with_explicit_organization_id() -> None:
    validate_safe_sql(
        "SELECT id, organization_id, filename FROM agent_document_overview "
        "WHERE status = 'completed'"
    )


def test_strips_trailing_semicolon() -> None:
    result = validate_safe_sql("SELECT * FROM agent_document_overview;")
    assert not result.endswith(";")


@pytest.mark.parametrize(
    "malicious_query",
    [
        "DROP TABLE agent_document_overview",
        "DELETE FROM agent_document_overview",
        "UPDATE agent_document_overview SET filename = 'x'",
        "INSERT INTO agent_document_overview VALUES (1)",
        "ALTER TABLE agent_document_overview ADD COLUMN x TEXT",
        "TRUNCATE agent_document_overview",
        "GRANT ALL ON agent_document_overview TO public",
        "SELECT * FROM agent_document_overview; DROP TABLE users",
        "CREATE TABLE evil (id INT)",
        "SELECT pg_sleep(10)",
        "SELECT * FROM agent_document_overview WHERE pg_sleep(5) IS NULL",
    ],
)
def test_rejects_write_and_dangerous_statements(malicious_query: str) -> None:
    with pytest.raises(SafeSqlError):
        validate_safe_sql(malicious_query)


def test_rejects_multiple_statements() -> None:
    with pytest.raises(SafeSqlError, match="Multiple statements"):
        validate_safe_sql("SELECT * FROM agent_document_overview; SELECT * FROM users")


def test_rejects_non_select_statements() -> None:
    with pytest.raises(SafeSqlError, match="Only SELECT"):
        validate_safe_sql("EXPLAIN SELECT * FROM agent_document_overview")


def test_rejects_comments() -> None:
    with pytest.raises(SafeSqlError, match="Comments"):
        validate_safe_sql("SELECT * FROM agent_document_overview -- sneaky comment")


def test_rejects_disallowed_table() -> None:
    with pytest.raises(SafeSqlError, match="disallowed table"):
        validate_safe_sql("SELECT * FROM users")


def test_rejects_join_to_disallowed_table() -> None:
    with pytest.raises(SafeSqlError, match="disallowed table"):
        validate_safe_sql(
            "SELECT * FROM agent_document_overview JOIN users "
            "ON users.id = agent_document_overview.id"
        )


def test_rejects_query_missing_organization_id_projection() -> None:
    with pytest.raises(SafeSqlError, match="organization_id"):
        validate_safe_sql("SELECT filename, status FROM agent_document_overview")


def test_rejects_empty_query() -> None:
    with pytest.raises(SafeSqlError, match="empty"):
        validate_safe_sql("   ")


def test_case_insensitive_keyword_detection() -> None:
    with pytest.raises(SafeSqlError):
        validate_safe_sql("drop table agent_document_overview")
    with pytest.raises(SafeSqlError):
        validate_safe_sql("DrOp TaBlE agent_document_overview")


def test_does_not_false_positive_on_column_names_containing_keywords() -> None:
    # A real risk of naive substring matching: a column/table name that
    # merely *contains* a forbidden keyword (e.g. "updated_at" contains
    # "update") must not be rejected — word-boundary matching should
    # distinguish "UPDATE" the statement from "updated_at" the column.
    result = validate_safe_sql(
        "SELECT *, updated_at FROM agent_document_overview WHERE created_at IS NOT NULL"
    )
    assert "updated_at" in result
