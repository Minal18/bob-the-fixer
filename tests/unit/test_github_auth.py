import time

import jwt
import responses
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from github_auth import create_app_jwt, get_installation_token

GITHUB_API = "https://api.github.com"

_RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PRIVATE_KEY_PEM = _RSA_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption(),
).decode()
PUBLIC_KEY_PEM = _RSA_KEY.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()


def test_create_app_jwt_sets_issuer_and_short_lived_expiry():
    before = int(time.time())
    token = create_app_jwt("app-123", PRIVATE_KEY_PEM)

    payload = jwt.decode(token, PUBLIC_KEY_PEM, algorithms=["RS256"])

    assert payload["iss"] == "app-123"
    # iat is backdated 60s for clock skew; exp is 9 min past the real "now" - so the
    # total iat..exp window is 10 min, matching GitHub's hard cap on App JWT lifetime.
    assert payload["iat"] <= before - 59
    assert payload["exp"] - before <= 9 * 60
    assert payload["exp"] - payload["iat"] == 10 * 60


@responses.activate
def test_get_installation_token_exchanges_jwt_for_installation_token():
    responses.add(
        responses.POST,
        f"{GITHUB_API}/app/installations/999/access_tokens",
        json={"token": "fake-installation-token"},
        status=200,
    )

    token = get_installation_token("app-123", PRIVATE_KEY_PEM, 999)

    assert token == "fake-installation-token"
    sent_auth_header = responses.calls[0].request.headers["Authorization"]
    assert sent_auth_header.startswith("Bearer ")

    sent_jwt = sent_auth_header.removeprefix("Bearer ")
    payload = jwt.decode(sent_jwt, PUBLIC_KEY_PEM, algorithms=["RS256"])
    assert payload["iss"] == "app-123"
