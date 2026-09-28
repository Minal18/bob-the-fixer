"""Cached Secrets Manager lookups shared across Lambdas."""
import boto3

_client = boto3.client("secretsmanager")
_cache: dict[str, str] = {}


def get_secret(secret_arn: str) -> str:
    if secret_arn not in _cache:
        response = _client.get_secret_value(SecretId=secret_arn)
        _cache[secret_arn] = response["SecretString"]
    return _cache[secret_arn]
