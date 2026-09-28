"""Worker Lambda: branches on GitHub event type.

pull_request  -> read Enablement Store; if enabled, review the diff and post inline comments.
issue_comment -> check for a @bob-the-fixer bot command; verify write access; update Enablement Store.

TODO(phase 4): GitHub App JWT -> installation token exchange (src/common/github_auth.py).
TODO(phase 4): fetch PR diff + repo config, call Claude, map findings to diff positions, post review.
TODO(phase 4): parse bot commands (enable/disable/status) and check collaborator permission.
"""
import json
import os

import boto3

dynamodb = boto3.resource("dynamodb")
enablement_table = dynamodb.Table(os.environ["ENABLEMENT_TABLE"])
posted_comments_table = dynamodb.Table(os.environ["POSTED_COMMENTS_TABLE"])


def handle_pull_request(payload: dict) -> None:
    repo_id = str(payload["repository"]["id"])
    item = enablement_table.get_item(Key={"repo_id": repo_id}).get("Item")
    if not item or not item.get("enabled"):
        return
    # TODO(phase 4): fetch diff + config, call Claude, post inline review comments,
    # write one row per comment to posted_comments_table.


def handle_issue_comment(payload: dict) -> None:
    comment_body = payload.get("comment", {}).get("body", "")
    if "@bob-the-fixer" not in comment_body:
        return
    # TODO(phase 4): parse command (enable/disable/status), verify commenter write access
    # via GitHub API, then write enablement_table.


def lambda_handler(event, context):
    for record in event["Records"]:
        message = json.loads(record["body"])
        github_event = message["github_event"]
        payload = message["payload"]

        if github_event == "pull_request":
            handle_pull_request(payload)
        elif github_event == "issue_comment":
            handle_issue_comment(payload)
