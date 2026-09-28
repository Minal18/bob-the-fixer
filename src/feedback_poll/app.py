"""Feedback Poll Lambda: runs on a fixed EventBridge schedule.

Queries the PostedDateIndex GSI for the last POLL_WINDOW_DAYS day-buckets,
checks each comment's current reaction counts via the GitHub Reactions API,
and overwrites the snapshot in the Feedback Metrics table.

TODO(phase 5): GitHub App JWT -> installation token exchange (shared with Worker).
TODO(phase 5): call the Reactions API per comment_id and write feedback_metrics_table.
"""
import os
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource("dynamodb")
posted_comments_table = dynamodb.Table(os.environ["POSTED_COMMENTS_TABLE"])
feedback_metrics_table = dynamodb.Table(os.environ["FEEDBACK_METRICS_TABLE"])
POLL_WINDOW_DAYS = int(os.environ.get("POLL_WINDOW_DAYS", "3"))


def _poll_window_dates() -> list[str]:
    today = datetime.now(timezone.utc).date()
    return [(today - timedelta(days=offset)).isoformat() for offset in range(POLL_WINDOW_DAYS)]


def lambda_handler(event, context):
    comments_to_check = []
    for date in _poll_window_dates():
        response = posted_comments_table.query(
            IndexName="PostedDateIndex",
            KeyConditionExpression=Key("posted_date").eq(date),
        )
        comments_to_check.extend(response.get("Items", []))

    # TODO(phase 5): for each comment, call the Reactions API and
    # feedback_metrics_table.put_item(...) with the current thumbs_up/thumbs_down snapshot.
    return {"checked": len(comments_to_check)}
