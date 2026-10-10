import base64

import pytest
import requests
import responses

from github_api import (
    get_collaborator_permission,
    get_pr_diff,
    get_repo_file,
    get_review_comments,
    post_issue_comment,
    post_review,
)

GITHUB_API = "https://api.github.com"


@responses.activate
def test_get_collaborator_permission_returns_permission_string():
    responses.add(
        responses.GET,
        f"{GITHUB_API}/repos/acme/widgets/collaborators/octocat/permission",
        json={"permission": "write"},
        status=200,
    )
    assert get_collaborator_permission("tok", "acme", "widgets", "octocat") == "write"
    assert responses.calls[0].request.headers["Authorization"] == "Bearer tok"


@responses.activate
def test_get_pr_diff_requests_diff_accept_header_and_returns_raw_text():
    diff_text = "diff --git a/foo.py b/foo.py\n--- a/foo.py\n+++ b/foo.py\n"
    responses.add(
        responses.GET,
        f"{GITHUB_API}/repos/acme/widgets/pulls/7",
        body=diff_text,
        status=200,
    )
    result = get_pr_diff("tok", "acme", "widgets", 7)
    assert result == diff_text
    assert responses.calls[0].request.headers["Accept"] == "application/vnd.github.v3.diff"


@responses.activate
def test_get_repo_file_decodes_base64_content():
    raw_content = "review_focus:\n  - bugs\n"
    encoded = base64.b64encode(raw_content.encode()).decode()
    responses.add(
        responses.GET,
        f"{GITHUB_API}/repos/acme/widgets/contents/.bob-the-fixer.yml",
        json={"content": encoded},
        status=200,
    )
    result = get_repo_file("tok", "acme", "widgets", ".bob-the-fixer.yml", "main")
    assert result == raw_content
    assert responses.calls[0].request.params["ref"] == "main"


@responses.activate
def test_get_repo_file_returns_none_on_404():
    responses.add(
        responses.GET,
        f"{GITHUB_API}/repos/acme/widgets/contents/.bob-the-fixer.yml",
        status=404,
    )
    assert get_repo_file("tok", "acme", "widgets", ".bob-the-fixer.yml", "main") is None


@responses.activate
def test_get_repo_file_raises_on_non_404_error():
    responses.add(
        responses.GET,
        f"{GITHUB_API}/repos/acme/widgets/contents/.bob-the-fixer.yml",
        status=500,
    )
    with pytest.raises(requests.exceptions.HTTPError):
        get_repo_file("tok", "acme", "widgets", ".bob-the-fixer.yml", "main")


@responses.activate
def test_post_review_sends_comments_and_returns_parsed_response():
    responses.add(
        responses.POST,
        f"{GITHUB_API}/repos/acme/widgets/pulls/7/reviews",
        json={"comments": [{"id": 555, "path": "foo.py", "line": 2}]},
        status=200,
    )
    comments = [{"path": "foo.py", "line": 2, "side": "RIGHT", "body": "looks risky"}]
    result = post_review("tok", "acme", "widgets", 7, comments)

    assert result["comments"][0]["id"] == 555
    sent_body = responses.calls[0].request.body
    assert b'"event": "COMMENT"' in sent_body or b'"event":"COMMENT"' in sent_body


@responses.activate
def test_get_review_comments_filters_to_just_this_review():
    responses.add(
        responses.GET,
        f"{GITHUB_API}/repos/acme/widgets/pulls/7/comments",
        json=[
            {"id": 555, "path": "foo.py", "line": 2, "pull_request_review_id": 42},
            {"id": 556, "path": "foo.py", "line": 5, "pull_request_review_id": 42},
            {"id": 999, "path": "foo.py", "line": 9, "pull_request_review_id": 7},  # from an earlier review
        ],
        status=200,
    )
    result = get_review_comments("tok", "acme", "widgets", 7, 42)
    assert {c["id"] for c in result} == {555, 556}


@responses.activate
def test_post_issue_comment_posts_body_text():
    responses.add(
        responses.POST,
        f"{GITHUB_API}/repos/acme/widgets/issues/9/comments",
        json={},
        status=201,
    )
    post_issue_comment("tok", "acme", "widgets", 9, "hello world")
    assert b"hello world" in responses.calls[0].request.body
