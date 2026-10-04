"""SQL validation for the run_safe_sql tool (spec §24, ADR-012 decision 3).

This module is layers 1-3 of the four-layer defense: statement shape,
keyword blocklist, table allowlist. Layer 4 (a database-enforced read-only
transaction) lives in safe_sql_tool.py's execution code, not here — this
module only ever produces a validated SQL string or raises, it never talks
to the database itself.

A real production system would likely use a proper SQL parser (e.g.
sqlglot) instead of regex for more robust validation — noted as a
reasonable future improvement, not implemented here to avoid an additional
dependency for what is, given layer 4's database-level enforcement, a
secondary defense rather than the sole safety mechanism.
"""

import re

ALLOWED_TABLES = frozenset({"agent_document_overview"})

_FORBIDDEN_KEYWORDS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
    "CREATE",
    "EXEC",
    "EXECUTE",
    "CALL",
    "COPY",
    "MERGE",
    "VACUUM",
    "REINDEX",
    "PG_SLEEP",
    "PG_READ_FILE",
    "DBLINK",
    "INTO",
)

_SELECT_FROM_RE = re.compile(r"(?is)^select\s+(.*?)\s+from\s+(.*)$")
_TABLE_REF_RE = re.compile(r"(?is)\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)")


class SafeSqlError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def validate_safe_sql(sql: str) -> str:
    """Returns the validated (trimmed) SQL string on success; raises
    SafeSqlError with a client-safe reason otherwise.
    """
    stripped = sql.strip()
    if stripped.endswith(";"):
        stripped = stripped[:-1].strip()
    if not stripped:
        raise SafeSqlError("Query is empty.")

    if ";" in stripped:
        raise SafeSqlError("Multiple statements are not allowed.")
    if "--" in stripped or "/*" in stripped:
        raise SafeSqlError("Comments are not allowed in the query.")
    if not re.match(r"(?is)^\s*select\b", stripped):
        raise SafeSqlError("Only SELECT statements are allowed.")

    for keyword in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", stripped, re.IGNORECASE):
            raise SafeSqlError(f"Keyword '{keyword}' is not allowed in this query.")

    match = _SELECT_FROM_RE.match(stripped)
    if not match:
        raise SafeSqlError("Could not parse a SELECT ... FROM ... structure.")
    select_clause = match.group(1)

    referenced_tables = {t.lower() for t in _TABLE_REF_RE.findall(stripped)}
    disallowed = referenced_tables - ALLOWED_TABLES
    if disallowed:
        allowed_list = ", ".join(sorted(ALLOWED_TABLES))
        raise SafeSqlError(
            f"Query references disallowed table(s): {', '.join(sorted(disallowed))}. "
            f"Only {allowed_list} may be queried."
        )
    if not referenced_tables:
        raise SafeSqlError("Query does not reference any allowed table.")

    if "*" not in select_clause and "organization_id" not in select_clause.lower():
        raise SafeSqlError(
            "Query must select '*' or explicitly include 'organization_id' in its "
            "column list so tenant scoping can be applied."
        )

    return stripped
