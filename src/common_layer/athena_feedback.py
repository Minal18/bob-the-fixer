"""Builds and runs the MERGE INTO statement that upserts a batch of feedback
rows straight into the Feedback Metrics Iceberg table via Athena - no
intermediate store, no export step.
"""
import time

_POLL_INTERVAL_SECONDS = 2
_MAX_POLL_SECONDS = 120
_TERMINAL_STATES = {"SUCCEEDED", "FAILED", "CANCELLED"}

_COLUMNS = ["comment_id", "repo_id", "pr_number", "file_path", "line", "thumbs_up", "thumbs_down", "checked_at"]


def _sql_literal(value) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if hasattr(value, "strftime"):
        return f"TIMESTAMP '{value.strftime('%Y-%m-%d %H:%M:%S')}'"
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def build_merge_sql(table: str, rows: list[dict]) -> str:
    columns_csv = ", ".join(_COLUMNS)
    values_rows = ",\n  ".join(
        "(" + ", ".join(_sql_literal(row[col]) for col in _COLUMNS) + ")" for row in rows
    )
    update_set = ", ".join(f"{col} = source.{col}" for col in _COLUMNS if col != "comment_id")
    insert_values = ", ".join(f"source.{col}" for col in _COLUMNS)
    return f"""MERGE INTO {table} AS target
USING (VALUES
  {values_rows}
) AS source({columns_csv})
ON target.comment_id = source.comment_id
WHEN MATCHED THEN UPDATE SET {update_set}
WHEN NOT MATCHED THEN INSERT ({columns_csv}) VALUES ({insert_values})"""


def run_merge(athena_client, workgroup: str, database: str, table: str, rows: list[dict]) -> None:
    if not rows:
        return

    query_id = athena_client.start_query_execution(
        QueryString=build_merge_sql(table, rows),
        QueryExecutionContext={"Database": database},
        WorkGroup=workgroup,
    )["QueryExecutionId"]

    elapsed = 0
    while elapsed <= _MAX_POLL_SECONDS:
        status = athena_client.get_query_execution(QueryExecutionId=query_id)["QueryExecution"]["Status"]
        if status["State"] in _TERMINAL_STATES:
            if status["State"] == "SUCCEEDED":
                return
            reason = status.get("StateChangeReason", "no reason given")
            raise RuntimeError(f"Athena MERGE query {query_id} ended in {status['State']}: {reason}")
        time.sleep(_POLL_INTERVAL_SECONDS)
        elapsed += _POLL_INTERVAL_SECONDS

    raise TimeoutError(f"Athena MERGE query {query_id} did not finish within {_MAX_POLL_SECONDS}s")
