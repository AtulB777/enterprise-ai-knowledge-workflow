"""run_safe_sql tool (spec §24). See ADR-012 decision 3 for the full
four-layer defense design; this file implements layer 4 — actual execution
inside a database-enforced read-only transaction, on a connection separate
from the agent's main session so it can never interfere with (or be
affected by) whatever else that session is doing.
"""

import datetime
import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db.session import get_engine
from app.models.agent_enums import ToolRiskLevel
from app.services.agents.tools.base import WRITE_ROLES, Tool, ToolExecutionContext, ToolResult
from app.services.agents.tools.safe_sql_validation import (
    ALLOWED_TABLES,
    SafeSqlError,
    validate_safe_sql,
)

_ROW_LIMIT = 50


class RunSafeSqlInput(BaseModel):
    query: str = Field(min_length=1, max_length=1000)


class RunSafeSqlOutput(BaseModel):
    # Row shape varies with the query's own column selection (within the
    # allowlisted view), so rows stay a flexible dict rather than a fixed
    # per-column schema — row_count and the container shape are what's
    # actually being validated here.
    rows: list[dict[str, Any]]
    row_count: int


class RunSafeSqlTool(Tool[RunSafeSqlInput]):
    name = "run_safe_sql"
    description = (
        "Runs a read-only SQL SELECT query against the 'agent_document_overview' view "
        "(columns: id, organization_id, filename, status, size_bytes, created_at, "
        "collection_name). Use SELECT * or explicitly include organization_id. "
        "No other tables are accessible, and no write statements are permitted."
    )
    risk_level = ToolRiskLevel.MEDIUM
    allowed_roles = WRITE_ROLES
    input_schema = RunSafeSqlInput
    output_schema = RunSafeSqlOutput

    async def _execute(
        self, arguments: RunSafeSqlInput, context: ToolExecutionContext
    ) -> ToolResult:
        try:
            validated_sql = validate_safe_sql(arguments.query)
        except SafeSqlError as exc:
            return ToolResult(success=False, output={}, error=exc.message)

        # Tenant scoping is applied here, by tool code, never by the LLM's
        # own SQL — the inner query only had to project organization_id
        # (enforced by validate_safe_sql); this outer wrapper is what
        # actually restricts results to the caller's own tenant.
        wrapped_sql = (
            f"SELECT * FROM ({validated_sql}) AS agent_query "
            f"WHERE organization_id = :org_id LIMIT {_ROW_LIMIT}"
        )

        engine = get_engine()
        try:
            async with engine.connect() as connection:
                # The real safety net: even if every string-level check
                # above had a gap, Postgres itself refuses any write here.
                await connection.execute(text("SET TRANSACTION READ ONLY"))
                result = await connection.execute(
                    text(wrapped_sql), {"org_id": str(context.organization_id)}
                )
                rows = [dict(row._mapping) for row in result.fetchall()]
        except Exception as exc:
            return ToolResult(success=False, output={}, error=f"Query execution failed: {exc}")

        serialized_rows = [_serialize_row(row) for row in rows]
        return ToolResult(
            success=True,
            output={"rows": serialized_rows, "row_count": len(serialized_rows)},
        )


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    serialized: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, uuid.UUID):
            serialized[key] = str(value)
        elif isinstance(value, datetime.datetime | datetime.date):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    return serialized


__all__ = ["RunSafeSqlTool", "RunSafeSqlInput", "ALLOWED_TABLES"]
