"""Unit tests for :mod:`qa_studio_cli.tui.form_builder`."""

from qa_studio_cli.tui.form_builder import (
    FieldSpec,
    build_fields,
    compute_overrides,
)


def _base_usecase() -> dict:
    return {
        "starting_url": "https://shop.example.com/",
        "executing_region": "us-east-1",
        "model_id": "nova-act-v1.0",
    }


class TestBuildFields:
    def test_always_includes_starting_url_and_runner_flags(self):
        fields = build_fields(_base_usecase(), {}, {}, [])
        sources = [f.source for f in fields]
        assert sources.count("starting_url") == 1
        # region, model_id, timeout
        assert sources.count("runner_flag") == 3
        assert [f.label for f in fields if f.source == "runner_flag"] == [
            "Region",
            "Model ID",
            "Timeout (s)",
        ]

    def test_starting_url_default_from_usecase(self):
        fields = build_fields(_base_usecase(), {}, {}, [])
        starting = next(f for f in fields if f.source == "starting_url")
        assert starting.default == "https://shop.example.com/"

    def test_variables_rendered_alphabetically(self):
        fields = build_fields(
            _base_usecase(),
            {"b": "2", "a": "1", "c": "3"},
            {},
            [],
        )
        var_names = [f.label for f in fields if f.source == "variable"]
        assert var_names == ["a", "b", "c"]

    def test_variable_default_is_declared_value(self):
        fields = build_fields(_base_usecase(), {"email": "dev@x"}, {}, [])
        email = next(f for f in fields if f.label == "email")
        assert email.default == "dev@x"
        assert email.is_secret is False

    def test_secrets_rendered_as_masked_with_empty_default(self):
        fields = build_fields(
            _base_usecase(), {}, {}, [{"key": "admin_pw", "value": "irrelevant"}]
        )
        secret = next(f for f in fields if f.source == "secret")
        assert secret.label == "admin_pw"
        assert secret.default == ""   # blank — stored value used on passthrough
        assert secret.is_secret is True

    def test_secret_without_key_is_skipped(self):
        """Malformed secret entry (missing key) must not break rendering."""
        fields = build_fields(_base_usecase(), {}, {}, [{"value": "orphan"}])
        assert not any(f.source == "secret" for f in fields)

    def test_keys_are_namespaced_by_source(self):
        """A variable called 'region' and the runner-flag 'region' must not collide."""
        fields = build_fields(_base_usecase(), {"region": "x"}, {}, [])
        keys = [f.key for f in fields]
        assert "variable:region" in keys
        assert "runner_flag:region" in keys


class TestComputeOverrides:
    def _fields_with_variable(self, name: str, default: str) -> list[FieldSpec]:
        return [
            FieldSpec(
                key=f"variable:{name}",
                label=name,
                default=default,
                is_secret=False,
                source="variable",
            )
        ]

    def test_unchanged_values_produce_empty_overrides(self):
        fields = self._fields_with_variable("email", "a@x")
        entered = {"variable:email": "a@x"}
        result = compute_overrides(fields, entered)
        assert result.variables == {}

    def test_changed_variable_appears_in_overrides(self):
        fields = self._fields_with_variable("email", "a@x")
        entered = {"variable:email": "b@x"}
        result = compute_overrides(fields, entered)
        assert result.variables == {"email": "b@x"}

    def test_empty_entered_value_is_no_override(self):
        """Documented POC limitation: can't clear to empty string."""
        fields = self._fields_with_variable("email", "a@x")
        entered = {"variable:email": ""}
        result = compute_overrides(fields, entered)
        assert result.variables == {}

    def test_missing_entry_is_treated_as_unchanged(self):
        fields = self._fields_with_variable("email", "a@x")
        result = compute_overrides(fields, {})
        assert result.variables == {}

    def test_starting_url_change_becomes_base_url(self):
        fields = [
            FieldSpec(
                key="starting_url:url",
                label="Starting URL",
                default="https://old/",
                is_secret=False,
                source="starting_url",
            )
        ]
        result = compute_overrides(fields, {"starting_url:url": "https://new/"})
        assert result.base_url == "https://new/"

    def test_unchanged_starting_url_leaves_base_url_none(self):
        fields = [
            FieldSpec(
                key="starting_url:url",
                label="Starting URL",
                default="https://x/",
                is_secret=False,
                source="starting_url",
            )
        ]
        result = compute_overrides(fields, {"starting_url:url": "https://x/"})
        assert result.base_url is None

    def test_header_override_collected(self):
        fields = [
            FieldSpec(
                key="header:Authorization",
                label="Authorization",
                default="Bearer old",
                is_secret=False,
                source="header",
            )
        ]
        result = compute_overrides(
            fields, {"header:Authorization": "Bearer new"}
        )
        assert result.headers == {"Authorization": "Bearer new"}

    def test_secret_with_value_is_included(self):
        """Secrets ignore the empty-means-no-override rule on the
        ``default`` comparison because their default is always ``""``
        — the rule for secrets is simply "non-empty entered ⇒ override"."""
        fields = [
            FieldSpec(
                key="secret:admin_pw",
                label="admin_pw",
                default="",
                is_secret=True,
                source="secret",
            )
        ]
        result = compute_overrides(fields, {"secret:admin_pw": "rotated"})
        assert result.secrets == {"admin_pw": "rotated"}

    def test_secret_left_blank_is_not_an_override(self):
        fields = [
            FieldSpec(
                key="secret:admin_pw",
                label="admin_pw",
                default="",
                is_secret=True,
                source="secret",
            )
        ]
        result = compute_overrides(fields, {"secret:admin_pw": ""})
        assert result.secrets == {}

    def test_runner_flag_change_collected(self):
        fields = [
            FieldSpec(
                key="runner_flag:region",
                label="Region",
                default="us-east-1",
                is_secret=False,
                source="runner_flag",
            ),
            FieldSpec(
                key="runner_flag:timeout",
                label="Timeout",
                default="3600",
                is_secret=False,
                source="runner_flag",
            ),
        ]
        result = compute_overrides(
            fields,
            {"runner_flag:region": "eu-west-1", "runner_flag:timeout": "3600"},
        )
        assert result.runner_flags == {"region": "eu-west-1"}

    def test_all_sources_combined(self):
        fields = build_fields(
            _base_usecase(),
            {"email": "a@x"},
            {"X-Trace": "abc"},
            [{"key": "pw", "value": ""}],
        )
        # Rewrite every field.
        entered = {
            "starting_url:url": "https://new/",
            "variable:email": "b@x",
            "header:X-Trace": "xyz",
            "secret:pw": "hunter2",
            "runner_flag:region": "eu-west-1",
            "runner_flag:model_id": "nova-act-v1.0",  # unchanged
            "runner_flag:timeout": "7200",
        }
        result = compute_overrides(fields, entered)
        assert result.base_url == "https://new/"
        assert result.variables == {"email": "b@x"}
        assert result.headers == {"X-Trace": "xyz"}
        assert result.secrets == {"pw": "hunter2"}
        assert result.runner_flags == {"region": "eu-west-1", "timeout": "7200"}
