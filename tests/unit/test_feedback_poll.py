import importlib.util
import os
import sys
from pathlib import Path

import boto3
import pytest
import responses
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from moto import mock_aws

GITHUB_API = "https://api.github.com"
FEEDBACK_POLL_APP = Path(__file__).resolve().parents[2] / "src" / "feedback_poll" / "app.py"

_RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
FAKE_PRIVATE_KEY_PEM = _RSA_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption(),
).decode()


def _load_feedback_poll_app():
    # Loaded under a distinct module name (not "app") since worker/app.py also
    # claims that name - importing both as "app" in the same test session would
    # silently alias one to the other via sys.modules.
    spec = importlib.util.spec_from_file_location("feedback_poll_app", FEEDBACK_POLL_APP)
    module = importlib.util.module_from_spec(spec)
    sys.modules["feedback_poll_app"] = module
    spec.loader.exec_module(module)
    return module


class _FakeAthenaClient:
    def __init__(self):
        self.merge_calls = []

    def start_query_execution(self, **kwargs):
        self.merge_calls.append(kwargs)
        return {"QueryExecutionId": "query-1"}

    def get_query_execution(self, QueryExecutionId):
        return {"QueryExecution": {"Status": {"State": "SUCCEEDED"}}}


@pytest.fixture()
def feedback_poll_app():
    with mock_aws():
        client = boto3.client("dynamodb", region_name=os.environ["AWS_DEFAULT_REGION"])
        client.create_table(
            TableName=os.environ["POSTED_COMMENTS_TABLE"],
            KeySchema=[{"AttributeName": "comment_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "comment_id", "AttributeType": "S"},
                {"AttributeName": "posted_date", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "PostedDateIndex",
                    "KeySchema": [{"AttributeName": "posted_date", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield _load_feedback_poll_app()


def _posted_comment(comment_id, posted_date, **overrides):
    item = {
        "comment_id": comment_id,
        "repo_id": "123456",
        "owner": "acme",
        "repo": "widgets",
        "installation_id": 999,
        "pr_number": 7,
        "file_path": "foo.py",
        "line": 2,
        "posted_date": posted_date,
    }
    item.update(overrides)
    return item


@responses.activate
def test_lambda_handler_merges_batch_from_posted_comments(feedback_poll_app, monkeypatch):
    import datetime

    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    feedback_poll_app.posted_comments_table.put_item(Item=_posted_comment("555", today))

    monkeypatch.setattr(feedback_poll_app, "get_secret", lambda arn: FAKE_PRIVATE_KEY_PEM)
    fake_athena = _FakeAthenaClient()
    monkeypatch.setattr(feedback_poll_app, "athena", fake_athena)

    responses.add(
        responses.POST,
        f"{GITHUB_API}/app/installations/999/access_tokens",
        json={"token": "fake-installation-token"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{GITHUB_API}/repos/acme/widgets/pulls/comments/555",
        json={"id": 555, "reactions": {"+1": 2, "-1": 0}},
        status=200,
    )

    result = feedback_poll_app.lambda_handler({"window_days": 3}, None)

    assert result == {"checked": 1, "merged": 1}
    assert len(fake_athena.merge_calls) == 1
    sql = fake_athena.merge_calls[0]["QueryString"]
    assert "'555'" in sql
    assert "thumbs_up = source.thumbs_up" in sql or "2" in sql


@responses.activate
def test_lambda_handler_reuses_installation_token_across_comments(feedback_poll_app, monkeypatch):
    import datetime

    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    feedback_poll_app.posted_comments_table.put_item(Item=_posted_comment("555", today))
    feedback_poll_app.posted_comments_table.put_item(Item=_posted_comment("556", today, line=5))

    monkeypatch.setattr(feedback_poll_app, "get_secret", lambda arn: FAKE_PRIVATE_KEY_PEM)
    fake_athena = _FakeAthenaClient()
    monkeypatch.setattr(feedback_poll_app, "athena", fake_athena)

    responses.add(
        responses.POST,
        f"{GITHUB_API}/app/installations/999/access_tokens",
        json={"token": "fake-installation-token"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{GITHUB_API}/repos/acme/widgets/pulls/comments/555",
        json={"id": 555, "reactions": {"+1": 1, "-1": 0}},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{GITHUB_API}/repos/acme/widgets/pulls/comments/556",
        json={"id": 556, "reactions": {"+1": 0, "-1": 1}},
        status=200,
    )

    result = feedback_poll_app.lambda_handler({"window_days": 3}, None)

    assert result == {"checked": 2, "merged": 2}
    token_calls = [c for c in responses.calls if "access_tokens" in c.request.url]
    assert len(token_calls) == 1  # cached across both comments, not re-minted


@responses.activate
def test_lambda_handler_skips_legacy_rows_missing_new_fields(feedback_poll_app, monkeypatch):
    import datetime

    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    # A row posted before owner/repo/installation_id existed - must be skipped, not crash the batch.
    legacy_item = {
        "comment_id": "111",
        "repo_id": "123456",
        "pr_number": 7,
        "file_path": "foo.py",
        "line": 2,
        "posted_date": today,
    }
    feedback_poll_app.posted_comments_table.put_item(Item=legacy_item)
    feedback_poll_app.posted_comments_table.put_item(Item=_posted_comment("555", today))

    monkeypatch.setattr(feedback_poll_app, "get_secret", lambda arn: FAKE_PRIVATE_KEY_PEM)
    fake_athena = _FakeAthenaClient()
    monkeypatch.setattr(feedback_poll_app, "athena", fake_athena)

    responses.add(
        responses.POST,
        f"{GITHUB_API}/app/installations/999/access_tokens",
        json={"token": "fake-installation-token"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{GITHUB_API}/repos/acme/widgets/pulls/comments/555",
        json={"id": 555, "reactions": {"+1": 1, "-1": 0}},
        status=200,
    )

    result = feedback_poll_app.lambda_handler({"window_days": 3}, None)

    assert result == {"checked": 2, "merged": 1}  # legacy row counted as checked, but not merged
    assert len(fake_athena.merge_calls) == 1
    assert "'111'" not in fake_athena.merge_calls[0]["QueryString"]


def test_lambda_handler_no_candidates_does_not_call_athena(feedback_poll_app, monkeypatch):
    fake_athena = _FakeAthenaClient()
    monkeypatch.setattr(feedback_poll_app, "athena", fake_athena)

    result = feedback_poll_app.lambda_handler({"window_days": 3}, None)

    assert result == {"checked": 0, "merged": 0}
    assert fake_athena.merge_calls == []
