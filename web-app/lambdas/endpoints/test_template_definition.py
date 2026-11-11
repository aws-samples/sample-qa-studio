"""``template_definition`` — the template file schema shared by ``POST /templates/import`` and ``PUT /templates/{id}``."""
import pytest
from pydantic import ValidationError

from template_definition import (
    TemplateDefinitionRequest,
    TemplateFileStep,
    placeholder_in_steps,
    step_rule_error,
    validation_message,
)
from repeat_validation import REPEAT_NOT_SUPPORTED_IN_TEMPLATES_ERROR


def _body(steps):
    return {"templateVersion": "1.0", "template": {"name": "Login"}, "steps": steps}


def _step(sort, **extra):
    return {"sort": sort, "step_type": "navigation", "instruction": f"step {sort}", **extra}


class TestStepId:
    def test_id_is_optional_and_kept(self):
        request = TemplateDefinitionRequest.model_validate(_body([_step(1, id="ts1"), _step(2)]))
        assert [s.id for s in request.steps] == ["ts1", None]

    def test_duplicate_ids_rejected(self):
        with pytest.raises(ValidationError) as excinfo:
            TemplateDefinitionRequest.model_validate(_body([_step(1, id="ts1"), _step(2, id="ts1")]))
        assert "steps: duplicate step id ts1" in validation_message(excinfo.value)

    def test_several_steps_without_id_are_fine(self):
        request = TemplateDefinitionRequest.model_validate(_body([_step(1), _step(2), _step(3)]))
        assert len(request.steps) == 3

    def test_extra_fields_pass_through(self):
        step = TemplateFileStep.model_validate(_step(1, browser_action="navigate", network_timeout=0))
        assert step.model_dump()["browser_action"] == "navigate"
        assert step.model_dump()["network_timeout"] == 0


class TestHelpers:
    def test_placeholder_in_steps(self):
        assert placeholder_in_steps([_step(1), {"sort": 2, "step_type": "template", "template_id": "x"}]) is True
        assert placeholder_in_steps([_step(1)]) is False
        assert placeholder_in_steps(None) is False
        assert placeholder_in_steps("nope") is False

    def test_step_rule_error_rejects_repeat(self):
        steps = TemplateDefinitionRequest.model_validate(_body([_step(1)])).steps
        assert step_rule_error(steps) is None
        repeat = TemplateFileStep.model_validate({"sort": 1, "step_type": "repeat", "instruction": "Loop",
                                                  "repeat_columns": ["a"], "repeat_rows": [["1"]]})
        assert step_rule_error([repeat]) == REPEAT_NOT_SUPPORTED_IN_TEMPLATES_ERROR

    def test_validation_message_joins_locations(self):
        with pytest.raises(ValidationError) as excinfo:
            TemplateDefinitionRequest.model_validate({"templateVersion": "2.0", "template": {}, "steps": []})
        message = validation_message(excinfo.value)
        assert "templateVersion" in message and "template.name" in message and "steps" in message
