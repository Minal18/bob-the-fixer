import os

import boto3
import pytest
import responses
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from moto import mock_aws

GITHUB_API = "https://api.github.com"

# Any syntactically valid RSA PEM works here: github_auth.create_app_jwt only needs
# something jwt.encode(..., algorithm="RS256") accepts. The installation-token HTTP
# call itself is stubbed below via `responses`, so its content is never checked.
_RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
FAKE_PRIVATE_KEY_PEM = _RSA_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption(),
).decode()


def _diff_text():
    return (
        "diff --git a/foo.py b/foo.py\n"
        "index e69de29..4b825dc 100644\n"
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@ -1,2 +1,3 @@\n"
        " line1\n"
        "+added_line\n"
        " line2\n"
    )


@pytest.fixture()
def worker_app():
    with mock_aws():
        client = boto3.client("dynamodb", region_name=os.environ["AWS_DEFAULT_REGION"])
        client.create_table(
            TableName=os.environ["ENABLEMENT_TABLE"],
            KeySchema=[{"AttributeName": "repo_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "repo_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
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

        import app  # noqa: PLC0415 - imported after tables + mocked AWS are ready

        yield app


def _pr_payload(repo_id="123456", owner="acme", repo="widgets", pr_number=7, installation_id=999, action="opened"):
    return {
        "action": action,
        "repository": {
            "id": int(repo_id),
            "owner": {"login": owner},
            "name": repo,
            "default_branch": "main",
        },
        "pull_request": {"number": pr_number},
        "installation": {"id": installation_id},
    }


@responses.activate
def test_handle_pull_request_posts_review_and_records_comment(worker_app, monkeypatch):
    repo_id = "123456"
    worker_app.enablement_table.put_item(Item={"repo_id": repo_id, "enabled": True})

    monkeypatch.setattr(worker_app, "get_secret", lambda arn: FAKE_PRIVATE_KEY_PEM)
    monkeypatch.setattr(
        worker_app,
        "review_diff",
        lambda api_key, diff, config: [
            {"file": "foo.py", "line": 2, "severity": "error", "comment": "looks risky"}
        ],
    )

    responses.add(
        responses.POST,
        f"{GITHUB_API}/app/installations/999/access_tokens",
        json={"token": "fake-installation-token"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{GITHUB_API}/repos/acme/widgets/contents/.bob-the-fixer.yml",
        status=404,
    )
    responses.add(
        responses.GET,
        f"{GITHUB_API}/repos/acme/widgets/pulls/7",
        body=_diff_text(),
        status=200,
    )
    # The real "Create a review" response has no "comments" field (GitHub API docs) -
    # the created inline comments are fetched separately via a review-scoped endpoint.
    responses.add(
        responses.POST,
        f"{GITHUB_API}/repos/acme/widgets/pulls/7/reviews",
        json={"id": 42, "state": "COMMENTED"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{GITHUB_API}/repos/acme/widgets/pulls/7/comments",
        json=[
            {"id": 555, "path": "foo.py", "line": 2, "pull_request_review_id": 42},
            {"id": 999, "path": "foo.py", "line": 9, "pull_request_review_id": 7},  # a different, earlier review
        ],
        status=200,
    )

    worker_app.handle_pull_request(_pr_payload(repo_id=repo_id))

    item = worker_app.posted_comments_table.get_item(Key={"comment_id": "555"}).get("Item")
    assert item is not None
    assert item["repo_id"] == repo_id
    assert item["pr_number"] == 7
    assert item["file_path"] == "foo.py"
    assert item["line"] == 2
    assert "posted_date" in item

    # comment 999 belongs to a different, earlier review - must not be recorded as if it were ours
    assert worker_app.posted_comments_table.get_item(Key={"comment_id": "999"}).get("Item") is None


@responses.activate
def test_handle_pull_request_skips_when_not_enabled(worker_app):
    # No enablement row written -> handle_pull_request must return before any
    # HTTP call. `responses.activate` with nothing registered turns any attempted
    # request into a ConnectionError, so this also proves no network call happened.
    worker_app.handle_pull_request(_pr_payload(repo_id="999999"))


@responses.activate
def test_handle_pull_request_drops_findings_below_severity_threshold(worker_app, monkeypatch):
    repo_id = "123456"
    worker_app.enablement_table.put_item(Item={"repo_id": repo_id, "enabled": True})

    monkeypatch.setattr(worker_app, "get_secret", lambda arn: FAKE_PRIVATE_KEY_PEM)
    monkeypatch.setattr(
        worker_app,
        "review_diff",
        lambda api_key, diff, config: [
            {"file": "foo.py", "line": 2, "severity": "info", "comment": "minor nit"}
        ],
    )

    responses.add(
        responses.POST,
        f"{GITHUB_API}/app/installations/999/access_tokens",
        json={"token": "fake-installation-token"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{GITHUB_API}/repos/acme/widgets/contents/.bob-the-fixer.yml",
        status=404,
    )
    responses.add(
        responses.GET,
        f"{GITHUB_API}/repos/acme/widgets/pulls/7",
        body=_diff_text(),
        status=200,
    )
    # No POST .../reviews stub registered: default_config's "warning" threshold
    # drops the "info" finding, so post_review must never be called.

    worker_app.handle_pull_request(_pr_payload(repo_id=repo_id))


@responses.activate
def test_handle_issue_comment_enable_requires_write_access(worker_app, monkeypatch):
    monkeypatch.setattr(worker_app, "get_secret", lambda arn: FAKE_PRIVATE_KEY_PEM)
    responses.add(
        responses.POST,
        f"{GITHUB_API}/app/installations/999/access_tokens",
        json={"token": "fake-installation-token"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{GITHUB_API}/repos/acme/widgets/collaborators/octocat/permission",
        json={"permission": "read"},
        status=200,
    )
    responses.add(
        responses.POST,
        f"{GITHUB_API}/repos/acme/widgets/issues/9/comments",
        json={},
        status=201,
    )

    payload = {
        "action": "created",
        "repository": {"id": 123456, "owner": {"login": "acme"}, "name": "widgets"},
        "issue": {"number": 9, "pull_request": {}},
        "comment": {"body": "@bob-the-fixer enable", "user": {"login": "octocat"}},
        "installation": {"id": 999},
    }
    worker_app.handle_issue_comment(payload)

    assert worker_app.enablement_table.get_item(Key={"repo_id": "123456"}).get("Item") is None


@responses.activate
def test_handle_issue_comment_enable_writes_enablement_store(worker_app, monkeypatch):
    monkeypatch.setattr(worker_app, "get_secret", lambda arn: FAKE_PRIVATE_KEY_PEM)
    responses.add(
        responses.POST,
        f"{GITHUB_API}/app/installations/999/access_tokens",
        json={"token": "fake-installation-token"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{GITHUB_API}/repos/acme/widgets/collaborators/octocat/permission",
        json={"permission": "write"},
        status=200,
    )
    responses.add(
        responses.POST,
        f"{GITHUB_API}/repos/acme/widgets/issues/9/comments",
        json={},
        status=201,
    )

    payload = {
        "action": "created",
        "repository": {"id": 123456, "owner": {"login": "acme"}, "name": "widgets"},
        "issue": {"number": 9, "pull_request": {}},
        "comment": {"body": "@bob-the-fixer enable", "user": {"login": "octocat"}},
        "installation": {"id": 999},
    }
    worker_app.handle_issue_comment(payload)

    item = worker_app.enablement_table.get_item(Key={"repo_id": "123456"}).get("Item")
    assert item is not None
    assert item["enabled"] is True
    assert item["enabled_by"] == "octocat"
