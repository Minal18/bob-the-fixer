"""Thin GitHub REST API client used by the Worker Lambda."""
import base64

import requests

GITHUB_API = "https://api.github.com"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def get_collaborator_permission(token: str, owner: str, repo: str, username: str) -> str:
    response = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/collaborators/{username}/permission",
        headers=_headers(token),
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["permission"]  # admin | write | read | none


def get_pr_diff(token: str, owner: str, repo: str, pr_number: int) -> str:
    response = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}",
        headers={**_headers(token), "Accept": "application/vnd.github.v3.diff"},
        timeout=10,
    )
    response.raise_for_status()
    return response.text


def get_repo_file(token: str, owner: str, repo: str, path: str, ref: str) -> str | None:
    response = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
        headers=_headers(token),
        params={"ref": ref},
        timeout=10,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return base64.b64decode(response.json()["content"]).decode()


def post_review(token: str, owner: str, repo: str, pr_number: int, comments: list[dict]) -> dict:
    response = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
        headers=_headers(token),
        json={"event": "COMMENT", "comments": comments},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def get_review_comments(token: str, owner: str, repo: str, pr_number: int, review_id: int) -> list[dict]:
    """The Create Review response has no 'comments' field, and the review-scoped
    .../reviews/{id}/comments endpoint returns the "Legacy Review Comment" shape,
    where `line`/`original_line` aren't reliably populated. Fetch all of the PR's
    review comments (current schema, which does populate `line`) and filter down
    to just the ones created by this review.
    """
    response = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/comments",
        headers=_headers(token),
        timeout=10,
    )
    response.raise_for_status()
    return [c for c in response.json() if c.get("pull_request_review_id") == review_id]


def post_issue_comment(token: str, owner: str, repo: str, issue_number: int, body: str) -> None:
    response = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues/{issue_number}/comments",
        headers=_headers(token),
        json={"body": body},
        timeout=10,
    )
    response.raise_for_status()
