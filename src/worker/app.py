"""Worker Lambda: branches on GitHub event type.

pull_request  -> read Enablement Store; if enabled, review the diff and post inline comments.
issue_comment -> parse a @bob-the-fixer bot command; verify write access; update Enablement Store.
"""
import json
import os
import re
from datetime import datetime, timezone

import boto3
from diff_utils import commentable_lines, filter_diff_by_ignore_paths
from github_api import (
    get_collaborator_permission,
    get_pr_diff,
    get_repo_file,
    get_review_comments,
    post_issue_comment,
    post_review,
)
from github_auth import get_installation_token
from repo_config import CONFIG_PATH, load_config
from reviewer import review_diff
from aws_secrets import get_secret

dynamodb = boto3.resource("dynamodb")
enablement_table = dynamodb.Table(os.environ["ENABLEMENT_TABLE"])
posted_comments_table = dynamodb.Table(os.environ["POSTED_COMMENTS_TABLE"])

GITHUB_APP_ID = os.environ["GITHUB_APP_ID"]
GITHUB_APP_PRIVATE_KEY_SECRET_ARN = os.environ["GITHUB_APP_PRIVATE_KEY_SECRET_ARN"]
ANTHROPIC_API_KEY_SECRET_ARN = os.environ["ANTHROPIC_API_KEY_SECRET_ARN"]

BOT_COMMAND = re.compile(r"@bob-the-fixer\s+(enable|disable|status)", re.IGNORECASE)
SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}


def _installation_token(installation_id: int) -> str:
    private_key = get_secret(GITHUB_APP_PRIVATE_KEY_SECRET_ARN)
    return get_installation_token(GITHUB_APP_ID, private_key, installation_id)


def handle_pull_request(payload: dict) -> None:
    if payload.get("action") not in ("opened", "synchronize", "reopened"):
        return

    repo_id = str(payload["repository"]["id"])
    item = enablement_table.get_item(Key={"repo_id": repo_id}).get("Item")
    if not item or not item.get("enabled"):
        return

    owner = payload["repository"]["owner"]["login"]
    repo = payload["repository"]["name"]
    pr_number = payload["pull_request"]["number"]
    default_branch = payload["repository"]["default_branch"]
    installation_id = payload["installation"]["id"]

    token = _installation_token(installation_id)

    # Config is read from the default branch, not the PR head — a PR can't loosen its own review policy.
    raw_config = get_repo_file(token, owner, repo, CONFIG_PATH, default_branch)
    config = load_config(raw_config)
    print(f"handle_pull_request: raw_config_present={raw_config is not None} config={config}")
    if config is None:
        print("handle_pull_request: malformed config, skipping")
        return  # malformed config: fail safe, skip review rather than fail loud

    diff = get_pr_diff(token, owner, repo, pr_number)
    diff = filter_diff_by_ignore_paths(diff, config["ignore_paths"])
    print(f"handle_pull_request: diff_len={len(diff)}")
    if not diff.strip():
        print("handle_pull_request: diff empty after filtering, skipping")
        return

    valid_lines = commentable_lines(diff)
    print(f"handle_pull_request: valid_lines={ {k: sorted(v) for k, v in valid_lines.items()} }")
    findings = review_diff(get_secret(ANTHROPIC_API_KEY_SECRET_ARN), diff, config)
    print(f"handle_pull_request: findings={findings}")

    threshold = SEVERITY_ORDER.get(config["severity_threshold"], 1)
    comments = []
    for finding in findings:
        if SEVERITY_ORDER.get(finding.get("severity"), 0) < threshold:
            print(f"handle_pull_request: dropping finding below threshold: {finding}")
            continue
        file_path, line = finding.get("file"), finding.get("line")
        if line not in valid_lines.get(file_path, set()):
            print(f"handle_pull_request: dropping finding with invalid position: {finding}")
            continue  # GitHub would reject a position outside the diff's visible hunks
        comments.append({"path": file_path, "line": line, "side": "RIGHT", "body": finding["comment"]})

    print(f"handle_pull_request: {len(comments)} comments to post")
    if not comments:
        return

    review = post_review(token, owner, repo, pr_number, comments)
    # The Create Review response has no "comments" field - the inline comments it just
    # created have to be fetched separately, scoped to this review's id.
    posted_comments = get_review_comments(token, owner, repo, pr_number, review["id"])
    print(f"handle_pull_request: posted_review_id={review['id']} posted_comments_count={len(posted_comments)}")
    posted_at = datetime.now(timezone.utc)
    for review_comment in posted_comments:
        posted_comments_table.put_item(Item={
            "comment_id": str(review_comment["id"]),
            "repo_id": repo_id,
            "pr_number": pr_number,
            "file_path": review_comment["path"],
            "line": review_comment.get("line") or review_comment.get("original_line"),
            "posted_at": posted_at.isoformat(),
            "posted_date": posted_at.date().isoformat(),
        })


def handle_issue_comment(payload: dict) -> None:
    action = payload.get("action")
    is_pr_comment = "pull_request" in payload.get("issue", {})
    if action != "created" or not is_pr_comment:
        print(f"handle_issue_comment: skipping, action={action!r} is_pr_comment={is_pr_comment}")
        return  # only react to new comments on a PR, not plain issues

    body = payload.get("comment", {}).get("body", "")
    match = BOT_COMMAND.search(body)
    if not match:
        print(f"handle_issue_comment: no bot command match in body={body!r}")
        return
    command = match.group(1).lower()
    print(f"handle_issue_comment: matched command={command!r}")

    repo_id = str(payload["repository"]["id"])
    owner = payload["repository"]["owner"]["login"]
    repo = payload["repository"]["name"]
    issue_number = payload["issue"]["number"]
    commenter = payload["comment"]["user"]["login"]
    installation_id = payload["installation"]["id"]

    token = _installation_token(installation_id)

    permission = get_collaborator_permission(token, owner, repo, commenter)
    if permission not in ("admin", "write"):
        post_issue_comment(token, owner, repo, issue_number,
                            f"@{commenter} you need write access to this repo to run that command.")
        return

    now = datetime.now(timezone.utc).isoformat()

    if command == "enable":
        enablement_table.put_item(Item={
            "repo_id": repo_id, "enabled": True, "enabled_by": commenter, "enabled_at": now,
        })
        post_issue_comment(token, owner, repo, issue_number, "Bob the Fixer is now **enabled** for this repo.")
    elif command == "disable":
        enablement_table.update_item(
            Key={"repo_id": repo_id},
            UpdateExpression="SET enabled = :f, disabled_at = :now",
            ExpressionAttributeValues={":f": False, ":now": now},
        )
        post_issue_comment(token, owner, repo, issue_number, "Bob the Fixer is now **disabled** for this repo.")
    elif command == "status":
        item = enablement_table.get_item(Key={"repo_id": repo_id}).get("Item")
        state = "enabled" if item and item.get("enabled") else "disabled"
        post_issue_comment(token, owner, repo, issue_number, f"Bob the Fixer is currently **{state}** for this repo.")


def lambda_handler(event, context):
    for record in event["Records"]:
        message = json.loads(record["body"])
        github_event = message["github_event"]
        payload = message["payload"]
        print(f"worker: github_event={github_event!r} action={payload.get('action')!r}")

        if github_event == "pull_request":
            handle_pull_request(payload)
        elif github_event == "issue_comment":
            handle_issue_comment(payload)
