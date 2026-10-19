"""Feedback Poll Lambda: a batch upsert job invoked by two EventBridge Scheduler
rules with different lookback windows - a frequent T-2/3 day delta pass (the
common case) and a weekly 30-day-bounded reconciliation pass, both running this
same code. For each candidate row from Posted Comments, checks the comment's
current reaction counts via the GitHub Reactions API, then merges the whole
batch straight into the Feedback Metrics Iceberg table via one Athena MERGE -
no intermediate DynamoDB table, no export step.
"""
import os
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Key

from athena_feedback import run_merge
from aws_secrets import get_secret
from github_api import get_comment_reactions
from github_auth import get_installation_token

dynamodb = boto3.resource("dynamodb")
athena = boto3.client("athena")
posted_comments_table = dynamodb.Table(os.environ["POSTED_COMMENTS_TABLE"])

GITHUB_APP_ID = os.environ["GITHUB_APP_ID"]
GITHUB_APP_PRIVATE_KEY_SECRET_ARN = os.environ["GITHUB_APP_PRIVATE_KEY_SECRET_ARN"]
ATHENA_WORKGROUP = os.environ["ATHENA_WORKGROUP"]
GLUE_DATABASE = os.environ["GLUE_DATABASE"]
GLUE_TABLE = os.environ["GLUE_TABLE"]
DEFAULT_POLL_WINDOW_DAYS = int(os.environ.get("POLL_WINDOW_DAYS", "3"))


def _poll_window_dates(window_days: int) -> list[str]:
    today = datetime.now(timezone.utc).date()
    return [(today - timedelta(days=offset)).isoformat() for offset in range(window_days)]


def _installation_token(installation_id: int, token_cache: dict[int, str]) -> str:
    if installation_id not in token_cache:
        private_key = get_secret(GITHUB_APP_PRIVATE_KEY_SECRET_ARN)
        token_cache[installation_id] = get_installation_token(GITHUB_APP_ID, private_key, installation_id)
    return token_cache[installation_id]


def lambda_handler(event, context):
    window_days = int((event or {}).get("window_days", DEFAULT_POLL_WINDOW_DAYS))

    comments_to_check = []
    for date in _poll_window_dates(window_days):
        response = posted_comments_table.query(
            IndexName="PostedDateIndex",
            KeyConditionExpression=Key("posted_date").eq(date),
        )
        comments_to_check.extend(response.get("Items", []))

    token_cache: dict[int, str] = {}
    checked_at = datetime.now(timezone.utc)
    rows = []
    for comment in comments_to_check:
        if not {"owner", "repo", "installation_id"} <= comment.keys():
            # Row predates the owner/repo/installation_id fields (posted before this
            # poll logic existed) - skip rather than crash the whole batch on it.
            print(f"lambda_handler: skipping legacy row missing owner/repo/installation_id: {comment.get('comment_id')}")
            continue
        token = _installation_token(int(comment["installation_id"]), token_cache)
        reactions = get_comment_reactions(token, comment["owner"], comment["repo"], int(comment["comment_id"]))
        rows.append({
            "comment_id": comment["comment_id"],
            "repo_id": comment["repo_id"],
            "pr_number": int(comment["pr_number"]),
            "file_path": comment["file_path"],
            "line": int(comment["line"]),
            "thumbs_up": reactions["thumbs_up"],
            "thumbs_down": reactions["thumbs_down"],
            "checked_at": checked_at,
        })

    run_merge(athena, ATHENA_WORKGROUP, GLUE_DATABASE, GLUE_TABLE, rows)
    return {"checked": len(comments_to_check), "merged": len(rows)}
