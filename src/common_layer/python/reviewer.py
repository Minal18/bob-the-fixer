"""Calls Claude to produce PR review findings, constrained to the supplied diff."""
import anthropic

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
                        "severity": {"type": "string", "enum": ["info", "warning", "error"]},
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

    prompt = f"""Review this pull request diff. Focus on: {focus}.
{custom_instructions}

Only flag lines that literally appear in the diff below (added '+' lines or unchanged
context lines) — never a line from outside this diff. Use the exact file path as shown
after "+++ b/" and the line number as it appears in the new version of the file.

<diff>
{diff_text}
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
