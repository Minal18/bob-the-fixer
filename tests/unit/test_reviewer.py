import reviewer


class _FakeBlock:
    def __init__(self, type_, name=None, input=None):
        self.type = type_
        self.name = name
        self.input = input


class _FakeResponse:
    def __init__(self, content):
        self.content = content


class _FakeMessages:
    def __init__(self, response, captured_calls):
        self._response = response
        self._captured_calls = captured_calls

    def create(self, **kwargs):
        self._captured_calls.append(kwargs)
        return self._response


class _FakeClient:
    def __init__(self, response, captured_calls):
        self.messages = _FakeMessages(response, captured_calls)


def _patch_anthropic(monkeypatch, response):
    captured_calls = []

    def fake_anthropic_constructor(api_key):
        return _FakeClient(response, captured_calls)

    monkeypatch.setattr(reviewer.anthropic, "Anthropic", fake_anthropic_constructor)
    return captured_calls


def test_review_diff_returns_findings_from_tool_use_block(monkeypatch):
    findings = [{"file": "foo.py", "line": 2, "severity": "error", "comment": "bug here"}]
    response = _FakeResponse([_FakeBlock("tool_use", name="report_findings", input={"findings": findings})])
    _patch_anthropic(monkeypatch, response)

    result = reviewer.review_diff("fake-key", "diff text", {"review_focus": ["bugs"], "custom_instructions": ""})

    assert result == findings


def test_review_diff_returns_empty_list_when_no_tool_use_block(monkeypatch):
    response = _FakeResponse([_FakeBlock("text")])
    _patch_anthropic(monkeypatch, response)

    result = reviewer.review_diff("fake-key", "diff text", {})

    assert result == []


def test_review_diff_prompt_includes_focus_and_custom_instructions(monkeypatch):
    response = _FakeResponse([_FakeBlock("tool_use", name="report_findings", input={"findings": []})])
    captured_calls = _patch_anthropic(monkeypatch, response)

    config = {"review_focus": ["security", "performance"], "custom_instructions": "Flag missing null checks."}
    reviewer.review_diff("fake-key", "<diff content>", config)

    prompt = captured_calls[0]["messages"][0]["content"]
    assert "security, performance" in prompt
    assert "Flag missing null checks." in prompt
    assert "<diff content>" in prompt
    assert captured_calls[0]["tool_choice"] == {"type": "tool", "name": "report_findings"}


def test_review_diff_prompt_includes_severity_rubric(monkeypatch):
    response = _FakeResponse([_FakeBlock("tool_use", name="report_findings", input={"findings": []})])
    captured_calls = _patch_anthropic(monkeypatch, response)

    reviewer.review_diff("fake-key", "diff text", {})

    prompt = captured_calls[0]["messages"][0]["content"]
    assert "Severity rubric" in prompt
    assert "error:" in prompt and "warning:" in prompt and "info:" in prompt

    severity_field = reviewer.FINDINGS_TOOL["input_schema"]["properties"]["findings"]["items"]["properties"]["severity"]
    assert "description" in severity_field
    assert "block merge" in severity_field["description"]
