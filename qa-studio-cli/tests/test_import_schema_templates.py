"""Template placeholder steps in test JSON and the template file schema."""

import pytest
from pydantic import ValidationError

from qa_studio_cli.models.import_schema import (
    VALID_STEP_TYPES,
    ExportPayload,
    ExportStep,
    TemplateFilePayload,
    TemplateRefStep,
)

LOGIN_ID = "3f1c0000-0000-4000-8000-000000000001"
SETUP_ID = "3f1c0000-0000-4000-8000-000000000002"


def _payload(steps, **extra):
    data = {
        "exportVersion": "1.0",
        "exportedAt": "2025-01-01T00:00:00Z",
        "usecase": {"name": "Checkout", "starting_url": "https://e.test"},
        "steps": steps,
    }
    data.update(extra)
    return data


def _placeholder(sort, template_id=LOGIN_ID, **extra):
    return {"sort": sort, "step_type": "template", "template_id": template_id, **extra}


def _step(sort, instruction="Click 'Add to cart'.", step_type="navigation", **extra):
    return {"sort": sort, "instruction": instruction, "step_type": step_type, **extra}


class TestTemplateRefStep:
    def test_valid_mixed_file(self):
        payload = ExportPayload.model_validate(
            _payload([_placeholder(1), _step(2), _step(3, "Return the badge count.", "validation",
                                                      validation_type="number", validation_operator="exact",
                                                      validation_value="1")])
        )
        assert isinstance(payload.steps[0], TemplateRefStep)
        assert isinstance(payload.steps[1], ExportStep)
        assert payload.steps[0].template_id == LOGIN_ID

    def test_template_is_not_an_executable_step_type(self):
        assert "template" not in VALID_STEP_TYPES

    @pytest.mark.parametrize("extra", [{"instruction": "Log in"}, {"secret_key": "x"}, {"steps": []}])
    def test_extra_field_rejected(self, extra):
        with pytest.raises(ValidationError, match="xtra"):
            ExportPayload.model_validate(_payload([_placeholder(1, **extra)]))

    @pytest.mark.parametrize("bad", ["not-a-uuid", "", "3f1c", "3f1c0000-0000-4000-8000-00000000000g"])
    def test_bad_uuid_rejected(self, bad):
        with pytest.raises(ValidationError, match="UUID"):
            ExportPayload.model_validate(_payload([_placeholder(1, bad)]))

    def test_missing_template_id_rejected(self):
        with pytest.raises(ValidationError, match="template_id"):
            ExportPayload.model_validate(_payload([{"sort": 1, "step_type": "template"}]))

    def test_sort_must_be_positive(self):
        with pytest.raises(ValidationError):
            ExportPayload.model_validate(_payload([_placeholder(0)]))

    def test_unknown_step_type_still_rejected(self):
        with pytest.raises(ValidationError, match="must be one of"):
            ExportPayload.model_validate(_payload([_step(1, step_type="teleport")]))

    def test_placeholder_inside_repeat_rejected(self):
        repeat = _step(1, "Loop", "repeat", repeat_columns=["a"], repeat_rows=[["1"]], steps=[_placeholder(1)])
        with pytest.raises(ValidationError):
            ExportPayload.model_validate(_payload([repeat]))

    def test_template_ids_distinct_in_order(self):
        payload = ExportPayload.model_validate(
            _payload([_placeholder(1, SETUP_ID), _step(2), _placeholder(3), _placeholder(4, SETUP_ID)])
        )
        assert payload.template_ids() == [SETUP_ID, LOGIN_ID]

    def test_template_ids_empty_without_placeholders(self):
        assert ExportPayload.model_validate(_payload([_step(1)])).template_ids() == []

    def test_placeholder_dumps_only_three_fields(self):
        payload = ExportPayload.model_validate(_payload([_placeholder(1), _step(2)]))
        dumped = payload.model_dump(by_alias=False)
        assert dumped["steps"][0] == {"sort": 1, "step_type": "template", "template_id": LOGIN_ID}
        # ExportStep keeps its historical dump shape (all optionals present)
        assert "instruction" in dumped["steps"][1]
        assert "secret_key" in dumped["steps"][1]


def _template_file(**overrides):
    data = {
        "templateVersion": "1.0",
        "template": {"name": "Login – Shop", "description": "Logs in", "category": "auth", "tags": ["shop"]},
        "steps": [
            _step(1, "Open login", "browser", browser_action="navigate", browser_args='{"url": "https://e.test"}'),
            _step(2, "Click into the username field.", "secret", secret_key="shop_username"),
            _step(3, "Click into the password field.", "secret", secret_key="shop_password"),
        ],
        "variables": [{"key": "base", "value": "https://e.test"}],
    }
    data.update(overrides)
    return data


class TestTemplateFilePayload:
    def test_valid_file(self):
        payload = TemplateFilePayload.model_validate(_template_file())
        assert payload.template.name == "Login – Shop"
        assert len(payload.steps) == 3
        assert all(isinstance(s, ExportStep) for s in payload.steps)
        assert payload.variables[0].key == "base"

    def test_defaults(self):
        payload = TemplateFilePayload.model_validate({"templateVersion": "1.0", "template": {"name": "x"},
                                                      "steps": [_step(1)]})
        assert payload.template.description == ""
        assert payload.template.category == ""
        assert payload.template.tags == []
        assert payload.variables == []

    def test_secret_keys_distinct_in_step_order(self):
        steps = _template_file()["steps"] + [_step(4, "Confirm password.", "secret", secret_key="shop_password")]
        payload = TemplateFilePayload.model_validate(_template_file(steps=steps))
        assert payload.secret_keys() == ["shop_username", "shop_password"]

    def test_placeholder_step_rejected(self):
        with pytest.raises(ValidationError, match="templates cannot contain template steps"):
            TemplateFilePayload.model_validate(_template_file(steps=[_step(1), _placeholder(2)]))

    def test_repeat_step_rejected(self):
        repeat = _step(1, "Loop", "repeat", repeat_columns=["a"], repeat_rows=[["1"]], steps=[_step(1)])
        with pytest.raises(ValidationError, match="repeat steps are not supported in templates"):
            TemplateFilePayload.model_validate(_template_file(steps=[repeat]))

    @pytest.mark.parametrize("overrides,fragment", [
        ({"templateVersion": "2.0"}, 'templateVersion must be "1.0"'),
        ({"template": {"name": ""}}, "name"),
        ({"template": {}}, "name"),
        ({"steps": []}, "steps"),
        ({"variables": [{"key": "", "value": "x"}]}, "key"),
    ], ids=["version", "empty-name", "missing-name", "no-steps", "variable-key"])
    def test_schema_errors(self, overrides, fragment):
        with pytest.raises(ValidationError, match=fragment):
            TemplateFilePayload.model_validate(_template_file(**overrides))

    def test_dump_round_trips_for_the_api(self):
        dumped = TemplateFilePayload.model_validate(_template_file()).model_dump(by_alias=False)
        assert dumped["templateVersion"] == "1.0"
        assert dumped["template"]["name"] == "Login – Shop"
        assert dumped["steps"][0]["browser_action"] == "navigate"
        assert dumped["variables"] == [{"key": "base", "value": "https://e.test"}]


class TestTemplateFileStepIds:
    """``steps[].id`` is the template step id emitted by ``templates export``; ``templates update`` matches on it."""

    def test_ids_are_optional_and_kept(self):
        steps = [_step(1, id="ts1"), _step(2)]
        payload = TemplateFilePayload.model_validate(_template_file(steps=steps))
        assert [s.id for s in payload.steps] == ["ts1", None]

    def test_without_ids_is_valid(self):
        payload = TemplateFilePayload.model_validate(_template_file())
        assert all(s.id is None for s in payload.steps)

    def test_duplicate_ids_rejected(self):
        steps = [_step(1, id="ts1"), _step(2, id="ts2"), _step(3, id="ts1")]
        with pytest.raises(ValidationError, match="steps: duplicate step id ts1"):
            TemplateFilePayload.model_validate(_template_file(steps=steps))
