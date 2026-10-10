import os

import boto3
from moto import mock_aws


def test_get_secret_fetches_value_and_caches_subsequent_calls():
    with mock_aws():
        client = boto3.client("secretsmanager", region_name=os.environ["AWS_DEFAULT_REGION"])
        created = client.create_secret(Name="bob-the-fixer/dev/test-secret", SecretString="s3cr3t-value")
        arn = created["ARN"]

        import aws_secrets
        aws_secrets._cache.clear()

        call_count = {"n": 0}
        real_get_secret_value = aws_secrets._client.get_secret_value

        def counting_get_secret_value(**kwargs):
            call_count["n"] += 1
            return real_get_secret_value(**kwargs)

        aws_secrets._client.get_secret_value = counting_get_secret_value

        try:
            first = aws_secrets.get_secret(arn)
            second = aws_secrets.get_secret(arn)
        finally:
            aws_secrets._client.get_secret_value = real_get_secret_value
            aws_secrets._cache.clear()

        assert first == "s3cr3t-value"
        assert second == "s3cr3t-value"
        assert call_count["n"] == 1  # second call served from _cache, no API call
