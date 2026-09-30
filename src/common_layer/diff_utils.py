"""Unified-diff helpers: which (file, line) targets GitHub's Review API will accept,
and dropping ignored files before the diff ever reaches the LLM.
"""
import fnmatch
import re

_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_FILE_HEADER = re.compile(r"^diff --git a/(.*) b/(.*)$", re.MULTILINE)


def commentable_lines(diff_text: str) -> dict[str, set[int]]:
    """Right-side (new-file) line numbers that fall inside a diff hunk, per file.
    GitHub's Review API rejects a comment on any line outside these.
    """
    result: dict[str, set[int]] = {}
    current_file = None
    new_line = None

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[len("+++ b/"):]
            result.setdefault(current_file, set())
            continue
        if line.startswith("+++ /dev/null"):
            current_file = None
            continue

        hunk_match = _HUNK_HEADER.match(line)
        if hunk_match:
            new_line = int(hunk_match.group(1))
            continue

        if current_file is None or new_line is None:
            continue

        if line.startswith("+"):
            result[current_file].add(new_line)
            new_line += 1
        elif line.startswith("-") or line.startswith("\\"):
            pass  # removed line, or "\ No newline at end of file" — no right-side line number
        else:
            result[current_file].add(new_line)  # unchanged context line
            new_line += 1

    return result


def filter_diff_by_ignore_paths(diff_text: str, ignore_paths: list[str]) -> str:
    if not ignore_paths:
        return diff_text

    matches = list(_FILE_HEADER.finditer(diff_text))
    if not matches:
        return diff_text

    kept = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(diff_text)
        file_path = match.group(2)
        if not any(fnmatch.fnmatch(file_path, pattern) for pattern in ignore_paths):
            kept.append(diff_text[start:end])

    return "".join(kept)
