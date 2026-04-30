"""Round-trip test: the sample testcase JSON must validate against both
the CLI-side and server-side validators.  Protects against schema drift
between the two."""

import json
from pathlib import Path


def _load_sample() -> dict:
    path = (
        Path(__file__).resolve().parents[2]
        / "testcases" / "operators" / "network_assertion_basic.json"
    )
    return json.loads(path.read_text())


def test_sample_passes_cli_validation():
    from qa_studio_cli.validation import validate_step

    sample = _load_sample()
    for step in sample["steps"]:
        ok, errors = validate_step(step)
        assert ok, f"sample step {step} failed CLI validation: {errors}"


def test_sample_step_has_expected_shape():
    sample = _load_sample()
    step = sample["steps"][0]
    assert step["step_type"] == "network_assertion"
    assert step["network_url_pattern"] == "**/api/users"
    assert step["network_body_match_type"] == "subset"
    assert isinstance(step["network_mock_passthrough"], bool)
    assert isinstance(step["network_timeout"], int)
    # Request body and mock response must be valid JSON strings.
    json.loads(step["network_request_body"])
    json.loads(step["network_mock_response"])


def test_full_flow_sample_passes_cli_validation():
    """E2E sample (testcases/app/network_assertion_full_flow.json) must
    validate against the CLI validator for every step."""
    import json
    from pathlib import Path

    from qa_studio_cli.validation import validate_step

    path = (
        Path(__file__).resolve().parents[2]
        / "testcases" / "app" / "network_assertion_full_flow.json"
    )
    sample = json.loads(path.read_text())
    for step in sample["steps"]:
        ok, errors = validate_step(step)
        assert ok, f"step {step.get('sort')} ({step.get('step_type')}) failed: {errors}"


def test_full_flow_sample_step_mix():
    """Sanity-check: the e2e sample exercises three step types in order."""
    import json
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[2]
        / "testcases" / "app" / "network_assertion_full_flow.json"
    )
    steps = json.loads(path.read_text())["steps"]
    types = [s["step_type"] for s in steps]
    assert types == ["network_assertion", "retrieve_value", "assertion"]
