from diff_utils import commentable_lines, filter_diff_by_ignore_paths


def test_commentable_lines_tracks_added_and_context_lines_not_removed():
    diff = (
        "diff --git a/foo.py b/foo.py\n"
        "index e69de29..4b825dc 100644\n"
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@ -1,3 +1,3 @@\n"
        " keep1\n"
        "-removed\n"
        "+added\n"
        " keep2\n"
    )
    lines = commentable_lines(diff)
    # new-file numbering: keep1=1, added=2 (takes removed's old slot), keep2=3.
    # "removed" never gets a new-side line number at all.
    assert lines["foo.py"] == {1, 2, 3}


def test_commentable_lines_handles_multiple_hunks_and_files():
    diff = (
        "diff --git a/a.py b/a.py\n"
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-old\n"
        "+new\n"
        "@@ -10,1 +10,2 @@\n"
        " ctx\n"
        "+added\n"
        "diff --git a/b.py b/b.py\n"
        "--- a/b.py\n"
        "+++ b/b.py\n"
        "@@ -1,1 +1,1 @@\n"
        "+only_line\n"
    )
    lines = commentable_lines(diff)
    assert lines["a.py"] == {1, 10, 11}
    assert lines["b.py"] == {1}


def test_commentable_lines_deleted_file_has_no_commentable_lines():
    diff = (
        "diff --git a/gone.py b/gone.py\n"
        "--- a/gone.py\n"
        "+++ /dev/null\n"
        "@@ -1,2 +0,0 @@\n"
        "-line1\n"
        "-line2\n"
    )
    lines = commentable_lines(diff)
    assert lines == {}


def test_commentable_lines_no_newline_at_end_of_file_marker_ignored():
    diff = (
        "diff --git a/foo.py b/foo.py\n"
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@ -1,1 +1,1 @@\n"
        "+added\n"
        "\\ No newline at end of file\n"
    )
    lines = commentable_lines(diff)
    assert lines["foo.py"] == {1}


def test_filter_diff_by_ignore_paths_empty_list_returns_diff_unchanged():
    diff = "diff --git a/foo.py b/foo.py\n--- a/foo.py\n+++ b/foo.py\n"
    assert filter_diff_by_ignore_paths(diff, []) == diff


def _multi_file_diff():
    return (
        "diff --git a/foo.py b/foo.py\n"
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-old\n"
        "+new\n"
        "diff --git a/package.lock b/package.lock\n"
        "--- a/package.lock\n"
        "+++ b/package.lock\n"
        "@@ -1,1 +1,1 @@\n"
        "-old\n"
        "+new\n"
        "diff --git a/vendor/thing/file.py b/vendor/thing/file.py\n"
        "--- a/vendor/thing/file.py\n"
        "+++ b/vendor/thing/file.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-old\n"
        "+new\n"
    )


def test_filter_diff_by_ignore_paths_drops_matching_files_including_nested_glob():
    filtered = filter_diff_by_ignore_paths(_multi_file_diff(), ["*.lock", "vendor/**"])
    assert "foo.py" in filtered
    assert "package.lock" not in filtered
    assert "vendor/thing/file.py" not in filtered


def test_filter_diff_by_ignore_paths_keeps_everything_when_nothing_matches():
    filtered = filter_diff_by_ignore_paths(_multi_file_diff(), ["*.md"])
    assert "foo.py" in filtered
    assert "package.lock" in filtered
    assert "vendor/thing/file.py" in filtered
