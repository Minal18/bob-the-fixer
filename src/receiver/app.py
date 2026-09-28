"""Webhook Receiver: verifies the GitHub signature and forwards the raw event to SQS."""
import hashlib
import hmac
import json
import os

import boto3
from secrets import get_secret  # provided by the CommonLayer

sqs = boto3.client("sqs")

WORKER_QUEUE_URL = os.environ["WORKER_QUEUE_URL"]
GITHUB_WEBHOOK_SECRET_ARN = os.environ["GITHUB_WEBHOOK_SECRET_ARN"]


def _verify_signature(body: str, signature_header: str | None) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    secret = get_secret(GITHUB_WEBHOOK_SECRET_ARN).encode()
    expected = hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature_header)


def lambda_handler(event, context):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    body = event.get("body", "")

    if not _verify_signature(body, headers.get("x-hub-signature-256")):
        return {"statusCode": 401, "body": "invalid signature"}

    github_event = headers.get("x-github-event", "")
    if github_event not in ("pull_request", "issue_comment"):
        # Ack anything else so GitHub doesn't retry; we just don't act on it.
        return {"statusCode": 202, "body": "ignored"}

    sqs.send_message(
        QueueUrl=WORKER_QUEUE_URL,
        MessageBody=json.dumps({"github_event": github_event, "payload": json.loads(body)}),
    )

    return {"statusCode": 202, "body": "queued"}
