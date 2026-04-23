from bughound_agent import BugHoundAgent
from llm_client import MockClient


class JsonMockClient:
    """Offline mock that returns controlled responses to test the LLM path without API calls."""

    def __init__(self, analysis_json: str, fix_code: str = "def f(): pass\n"):
        self._analysis_json = analysis_json
        self._fix_code = fix_code

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if "Return ONLY valid JSON" in system_prompt:
            return self._analysis_json
        return self._fix_code


def test_workflow_runs_in_offline_mode_and_returns_shape():
    agent = BugHoundAgent(client=None)  # heuristic-only
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    assert isinstance(result, dict)
    assert "issues" in result
    assert "fixed_code" in result
    assert "risk" in result
    assert "logs" in result

    assert isinstance(result["issues"], list)
    assert isinstance(result["fixed_code"], str)
    assert isinstance(result["risk"], dict)
    assert isinstance(result["logs"], list)
    assert len(result["logs"]) > 0


def test_offline_mode_detects_print_issue():
    agent = BugHoundAgent(client=None)
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    assert any(issue.get("type") == "Code Quality" for issue in result["issues"])


def test_offline_mode_proposes_logging_fix_for_print():
    agent = BugHoundAgent(client=None)
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    fixed = result["fixed_code"]
    assert "logging" in fixed
    assert "logging.info(" in fixed


def test_mock_client_forces_llm_fallback_to_heuristics_for_analysis():
    # MockClient returns non-JSON for analyzer prompts, so agent should fall back.
    agent = BugHoundAgent(client=MockClient())
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    assert any(issue.get("type") == "Code Quality" for issue in result["issues"])
    # Ensure we logged the fallback path
    assert any("Falling back to heuristics" in entry.get("message", "") for entry in result["logs"])


def test_llm_path_uses_valid_json_without_fallback():
    # JsonMockClient returns parseable JSON → agent uses it directly, no fallback
    valid_json = '[{"type": "Security", "severity": "High", "msg": "Hardcoded credential detected."}]'
    agent = BugHoundAgent(client=JsonMockClient(valid_json, fix_code="import os\nAPI_KEY = os.getenv('KEY')\n"))
    result = agent.run("API_KEY = 'abc123'\n")

    assert result["issues"] == [{"type": "Security", "severity": "High", "msg": "Hardcoded credential detected."}]
    assert not any("Falling back" in e["message"] for e in result["logs"])
    assert result["risk"]["should_autofix"] is False  # High severity → no autofix


def test_llm_path_falls_back_when_issue_msg_is_empty():
    # Plan A: issues with empty msg are dropped → _normalize_issues returns None → heuristic fallback
    bad_json = '[{"type": "Bug", "severity": "High", "msg": ""}]'
    agent = BugHoundAgent(client=JsonMockClient(bad_json))
    result = agent.run("def f():\n    print('hi')\n")

    assert any("Falling back" in e["message"] for e in result["logs"])
    assert any(i["type"] == "Code Quality" for i in result["issues"])


def test_llm_path_falls_back_when_all_issues_are_blank_dicts():
    # Plan A: dicts missing type and msg are all dropped → None → heuristic fallback
    agent = BugHoundAgent(client=JsonMockClient('[{}, {}, {}]'))
    result = agent.run("def f():\n    print('hi')\n")

    assert any("Falling back" in e["message"] for e in result["logs"])
    assert any(i["type"] == "Code Quality" for i in result["issues"])
