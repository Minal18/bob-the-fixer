"""Unified-diff helpers: which (file, line) targets GitHub's Review API will accept,
annotating diff text with new-file line numbers before it goes to the LLM (so the LLM
can copy a position instead of counting it), and dropping ignored files before the
diff ever reaches the LLM.
"""
import fnmatch
import re

_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_FILE_HEADER = re.compile(r"^diff --git a/(.*) b/(.*)$", re.MULTILINE)


def _walk_diff_lines(diff_text: str):
    """Yields (file, new_line, raw_line) for every line in diff_text.
    new_line is the right-side (new-file) line number if this line has one (an added
    '+' line or unchanged context line), else None — file/hunk headers and removed
    '-' lines have no position in the new file.
    """
    current_file = None
    new_line = None

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            # Start of the next file's header block ("diff --git", "index ...", "---").
            # Without this, those lines fall through to the trailing `else` below and
            # get miscounted as a trailing context line of the *previous* file.
            current_file = None
            new_line = None
            yield current_file, None, line
            continue
        if line.startswith("+++ b/"):
            current_file = line[len("+++ b/"):]
            yield current_file, None, line
            continue
        if line.startswith("+++ /dev/null"):
            current_file = None
            yield current_file, None, line
            continue

        hunk_match = _HUNK_HEADER.match(line)
        if hunk_match:
            new_line = int(hunk_match.group(1))
            yield current_file, None, line
            continue

        if current_file is None or new_line is None:
            yield current_file, None, line
            continue

        if line.startswith("+"):
            yield current_file, new_line, line
            new_line += 1
        elif line.startswith("-") or line.startswith("\\"):
            yield current_file, None, line  # removed line, or "\ No newline at end of file"
        else:
            yield current_file, new_line, line  # unchanged context line
            new_line += 1


def commentable_lines(diff_text: str) -> dict[str, set[int]]:
    """Right-side (new-file) line numbers that fall inside a diff hunk, per file.
    GitHub's Review API rejects a comment on any line outside these.
    """
    result: dict[str, set[int]] = {}
    for file, new_line, _ in _walk_diff_lines(diff_text):
        if file is None:
            continue
        result.setdefault(file, set())
        if new_line is not None:
            result[file].add(new_line)
    return result


def annotate_diff_with_line_numbers(diff_text: str) -> str:
    """Prefixes each added or context line with its right-side (new-file) line
    number, e.g. "42: +    foo()", so an LLM reviewing the diff can read off the
    position of a line it wants to comment on instead of counting lines itself.
    File headers, hunk headers, and removed '-' lines are left unprefixed since
    they have no new-file line number.
    """
    out = []
    for _, new_line, raw_line in _walk_diff_lines(diff_text):
        out.append(f"{new_line}: {raw_line}" if new_line is not None else raw_line)
    return "\n".join(out)


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
