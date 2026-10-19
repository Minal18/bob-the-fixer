import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "common_layer"))
sys.path.insert(0, str(ROOT / "src" / "worker"))

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")

os.environ.setdefault("STAGE", "dev")
os.environ.setdefault("ENABLEMENT_TABLE", "test-bob-enablement")
os.environ.setdefault("POSTED_COMMENTS_TABLE", "test-bob-posted-comments")
os.environ.setdefault("GITHUB_APP_ID", "12345")
os.environ.setdefault(
    "GITHUB_APP_PRIVATE_KEY_SECRET_ARN",
    "arn:aws:secretsmanager:us-east-1:000000000000:secret:fake-private-key",
)
os.environ.setdefault(
    "ANTHROPIC_API_KEY_SECRET_ARN",
    "arn:aws:secretsmanager:us-east-1:000000000000:secret:fake-anthropic-key",
)
os.environ.setdefault("ATHENA_WORKGROUP", "test-bob-analytics")
os.environ.setdefault("GLUE_DATABASE", "test_bob_analytics")
os.environ.setdefault("GLUE_TABLE", "feedback_metrics")
