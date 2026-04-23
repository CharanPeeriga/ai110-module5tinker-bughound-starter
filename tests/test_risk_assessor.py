from reliability.risk_assessor import assess_risk
from bughound_agent import BugHoundAgent


def test_no_fix_is_high_risk():
    risk = assess_risk(
        original_code="print('hi')\n",
        fixed_code="",
        issues=[{"type": "Code Quality", "severity": "Low", "msg": "print"}],
    )
    assert risk["level"] == "high"
    assert risk["should_autofix"] is False
    assert risk["score"] == 0


def test_low_risk_when_minimal_change_and_low_severity():
    original = "import logging\n\ndef add(a, b):\n    return a + b\n"
    fixed = "import logging\n\ndef add(a, b):\n    logging.info('adding')\n    return a + b\n"
    risk = assess_risk(
        original_code=original,
        fixed_code=fixed,
        issues=[{"type": "Code Quality", "severity": "Low", "msg": "minor"}],
    )
    # Low severity only deducts 5 points → score 95 → level "low"
    assert risk["score"] == 95
    assert risk["level"] == "low"
    assert risk["should_autofix"] is True


def test_high_severity_issue_drives_score_down():
    original = "def f():\n    try:\n        return 1\n    except:\n        return 0\n"
    fixed = "def f():\n    try:\n        return 1\n    except Exception as e:\n        return 0\n"
    risk = assess_risk(
        original_code=original,
        fixed_code=fixed,
        issues=[{"type": "Reliability", "severity": "High", "msg": "bare except"}],
    )
    # High severity (-40) + bare except modified (-5) → score 55 → level "medium"
    assert risk["score"] == 55
    assert risk["level"] == "medium"
    assert risk["should_autofix"] is False


def test_missing_return_is_penalized():
    original = "def f(x):\n    return x + 1\n"
    fixed = "def f(x):\n    x + 1\n"
    risk = assess_risk(
        original_code=original,
        fixed_code=fixed,
        issues=[],
    )
    # Removed return statement deducts 30 points → score 70 → level "medium"
    assert risk["score"] == 70
    assert risk["level"] == "medium"
    assert risk["should_autofix"] is False
    assert any("Return statements may have been removed" in r for r in risk["reasons"])


def test_agent_does_not_autofix_high_severity_issue_end_to_end():
    # Full pipeline: heuristics detect bare except (High) → risk assessed → no autofix
    # client=None ensures no API call is made
    agent = BugHoundAgent(client=None)
    code = "def f():\n    try:\n        return 1\n    except:\n        return 0\n"
    result = agent.run(code)

    # High severity (-40) + bare except modified (-5) → score 55 → level "medium"
    assert result["risk"]["score"] == 55
    assert result["risk"]["level"] == "medium"
    assert result["risk"]["should_autofix"] is False
