"""Tests for browser and transform schema fields on UseCaseStep."""

from qa_studio_cli.models.execution import UseCaseStep


class TestUseCaseStepNewFields:
    """Verify the four new optional fields on UseCaseStep."""

    def test_defaults_are_none(self):
        s = UseCaseStep(step_id="s1", step_type="navigation", instruction="Click", sort=1)
        assert s.browser_action is None
        assert s.browser_args is None
        assert s.transform_operation is None
        assert s.transform_args is None

    def test_browser_step(self):
        s = UseCaseStep(
            step_id="s1", step_type="browser", instruction="", sort=1,
            browser_action="reload", browser_args='{"hard": false}',
        )
        assert s.browser_action == "reload"
        assert s.browser_args == '{"hard": false}'

    def test_transform_step(self):
        s = UseCaseStep(
            step_id="s1", step_type="transform", instruction="", sort=1,
            transform_operation="math",
            transform_args='{"expression": "{{ price }} * 1.2"}',
            capture_variable="total",
        )
        assert s.transform_operation == "math"
        assert s.capture_variable == "total"

    def test_serialization_round_trip(self):
        s = UseCaseStep(
            step_id="s1", step_type="browser", instruction="", sort=1,
            browser_action="back",
        )
        data = s.model_dump()
        restored = UseCaseStep(**data)
        assert restored.browser_action == "back"
        assert restored.transform_operation is None
