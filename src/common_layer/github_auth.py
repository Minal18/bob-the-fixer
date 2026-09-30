"""GitHub App authentication: JWT signing and installation-token exchange."""
import time

import jwt
import requests

GITHUB_API = "https://api.github.com"


def create_app_jwt(app_id: str, private_key_pem: str) -> str:
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 9 * 60, "iss": app_id}
    return jwt.encode(payload, private_key_pem, algorithm="RS256")


def get_installation_token(app_id: str, private_key_pem: str, installation_id: int) -> str:
    app_jwt = create_app_jwt(app_id, private_key_pem)
    response = requests.post(
        f"{GITHUB_API}/app/installations/{installation_id}/access_tokens",
        headers={"Authorization": f"Bearer {app_jwt}", "Accept": "application/vnd.github+json"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["token"]
