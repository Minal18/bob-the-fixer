"""Calls Claude to produce PR review findings, constrained to the supplied diff."""
import anthropic

from diff_utils import annotate_diff_with_line_numbers

MODEL = "claude-sonnet-5"

FINDINGS_TOOL = {
    "name": "report_findings",
    "description": "Report PR review findings found in the diff.",
    "input_schema": {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string", "description": "Exact path as shown after '+++ b/' in the diff"},
                        "line": {"type": "integer", "description": "New-file line number, as it appears in the diff"},
                        "severity": {
                            "type": "string",
                            "enum": ["info", "warning", "error"],
                            "description": (
                                "error: will cause incorrect behavior, a crash, data loss, or is an "
                                "exploitable security issue - should block merge. warning: a real "
                                "problem that should be fixed before merge but isn't immediately "
                                "dangerous (e.g. an unhandled edge case, inconsistent error handling). "
                                "info: minor, stylistic, or a nice-to-have - not a functional risk."
                            ),
                        },
                        "comment": {"type": "string"},
                    },
                    "required": ["file", "line", "severity", "comment"],
                },
            }
        },
        "required": ["findings"],
    },
}


def review_diff(api_key: str, diff_text: str, config: dict) -> list[dict]:
    client = anthropic.Anthropic(api_key=api_key)

    focus = ", ".join(config.get("review_focus") or ["bugs", "security"])
    custom_instructions = config.get("custom_instructions") or ""
    annotated_diff = annotate_diff_with_line_numbers(diff_text)

    prompt = f"""Review this pull request diff. Focus on: {focus}.
{custom_instructions}

Only flag lines that literally appear in the diff below (added '+' lines or unchanged
context lines) — never a line from outside this diff. Use the exact file path as shown
after "+++ b/".

Each added or context line below is prefixed with "N: " where N is its exact line
number in the new version of the file (e.g. "42: +    foo()"). Read that number off
the line you want to comment on and report it as-is — do not count lines yourself.
Lines without an "N: " prefix (file/hunk headers, removed '-' lines) have no line
number and can't be commented on.

Severity rubric — classify each finding by its actual impact, not by how it feels:
- error: will cause incorrect behavior, a crash, data loss, or is an exploitable security
  issue. Should block merge.
- warning: a real problem that should be fixed before merge, but isn't immediately
  dangerous — e.g. an unhandled edge case, inconsistent error handling, a bug that only
  triggers on a specific input.
- info: minor, stylistic, or a nice-to-have improvement. Not a functional risk.

<diff>
{annotated_diff}
</diff>"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        tools=[FINDINGS_TOOL],
        tool_choice={"type": "tool", "name": "report_findings"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "report_findings":
            return block.input.get("findings", [])
    return []
