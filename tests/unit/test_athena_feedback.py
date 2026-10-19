from datetime import datetime, timezone

import pytest

from athena_feedback import build_merge_sql, run_merge


def _row(**overrides):
    row = {
        "comment_id": "555",
        "repo_id": "123456",
        "pr_number": 7,
        "file_path": "foo.py",
        "line": 2,
        "thumbs_up": 3,
        "thumbs_down": 1,
        "checked_at": datetime(2026, 10, 19, 18, 0, 0, tzinfo=timezone.utc),
    }
    row.update(overrides)
    return row


def test_build_merge_sql_shapes_values_and_match_clauses():
    sql = build_merge_sql("feedback_metrics", [_row()])

    assert "MERGE INTO feedback_metrics AS target" in sql
    assert "'555'" in sql
    assert "'123456'" in sql
    assert "'foo.py'" in sql
    assert "TIMESTAMP '2026-10-19 18:00:00'" in sql
    assert "WHEN MATCHED THEN UPDATE SET" in sql
    assert "thumbs_up = source.thumbs_up" in sql
    update_set_clause = sql.split("WHEN MATCHED THEN UPDATE SET")[1].split("WHEN NOT MATCHED")[0]
    assert "comment_id = source.comment_id" not in update_set_clause  # merge key excluded from UPDATE SET
    assert "WHEN NOT MATCHED THEN INSERT" in sql


def test_build_merge_sql_escapes_single_quotes_in_strings():
    sql = build_merge_sql("feedback_metrics", [_row(file_path="it's_tricky.py")])
    assert "'it''s_tricky.py'" in sql


def test_build_merge_sql_includes_one_values_row_per_input_row():
    sql = build_merge_sql("feedback_metrics", [_row(comment_id="1"), _row(comment_id="2")])
    assert "'1'" in sql
    assert "'2'" in sql


class _FakeAthenaClient:
    def __init__(self, states):
        self._states = list(states)
        self.started_with = None

    def start_query_execution(self, **kwargs):
        self.started_with = kwargs
        return {"QueryExecutionId": "query-1"}

    def get_query_execution(self, QueryExecutionId):
        state = self._states.pop(0) if len(self._states) > 1 else self._states[0]
        return {"QueryExecution": {"Status": {"State": state, "StateChangeReason": "boom"}}}


def test_run_merge_does_nothing_when_no_rows():
    client = _FakeAthenaClient(["SUCCEEDED"])
    run_merge(client, "wg", "db", "feedback_metrics", [])
    assert client.started_with is None


def test_run_merge_polls_until_succeeded(monkeypatch):
    monkeypatch.setattr("athena_feedback.time.sleep", lambda seconds: None)
    client = _FakeAthenaClient(["RUNNING", "RUNNING", "SUCCEEDED"])

    run_merge(client, "wg", "db", "feedback_metrics", [_row()])

    assert client.started_with["WorkGroup"] == "wg"
    assert client.started_with["QueryExecutionContext"] == {"Database": "db"}


def test_run_merge_raises_on_failed_query(monkeypatch):
    monkeypatch.setattr("athena_feedback.time.sleep", lambda seconds: None)
    client = _FakeAthenaClient(["FAILED"])

    with pytest.raises(RuntimeError, match="boom"):
        run_merge(client, "wg", "db", "feedback_metrics", [_row()])
