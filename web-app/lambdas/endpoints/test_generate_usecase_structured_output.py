"""Unit tests for structured output schema and Bedrock integration.

Tests cover:
- USECASE_EXPORT_SCHEMA: schema structure and field definitions
- _get_tool_config: correct Converse API toolConfig format
- invoke_bedrock: passes toolConfig, handles tool use response, extended thinking
- create_prompt: no longer contains inline JSON example
"""
import json
import os
import pytest
from unittest.mock import patch, MagicMock

os.environ.setdefault('TABLE_NAME', 'test-table')
os.environ.setdefault('BUCKET_NAME', 'test-bucket')
os.environ.setdefault('BEDROCK_MODEL_ID', 'test-model')

from generate_usecase import (
    USECASE_EXPORT_SCHEMA,
    _get_tool_config,
    _is_nova2_model,
    create_prompt,
    invoke_bedrock,
    extract_json,
)


# --- USECASE_EXPORT_SCHEMA tests ---

class TestUsecaseExportSchema:
    """Tests for the JSON schema definition."""

    def test_schema_is_valid_json_serializable(self):
        """Schema must be JSON-serializable (required by Bedrock API)."""
        serialized = json.dumps(USECASE_EXPORT_SCHEMA)
        parsed = json.loads(serialized)
        assert parsed['type'] == 'object'

    def test_schema_has_required_top_level_fields(self):
        required = USECASE_EXPORT_SCHEMA['required']
        assert 'exportVersion' in required
        assert 'exportedAt' in required
        assert 'usecase' in required
        assert 'steps' in required
        assert 'variables' in required
        assert 'secrets' in required
        assert 'hooks' in required

    def test_schema_disallows_additional_properties(self):
        assert USECASE_EXPORT_SCHEMA['additionalProperties'] is False

    def test_usecase_subschema_has_required_fields(self):
        usecase = USECASE_EXPORT_SCHEMA['properties']['usecase']
        assert 'name' in usecase['properties']
        assert 'starting_url' in usecase['properties']
        assert 'executing_region' in usecase['properties']
        assert usecase['additionalProperties'] is False

    def test_step_subschema_has_all_fields(self):
        step = USECASE_EXPORT_SCHEMA['properties']['steps']['items']
        expected_fields = [
            'sort', 'instruction', 'step_type', 'secret_key',
            'capture_variable', 'validation_type', 'validation_operator',
            'validation_value', 'assertion_variable', 'value_step', 'value_type',
        ]
        for field in expected_fields:
            assert field in step['properties'], f'Missing step field: {field}'
        assert set(step['required']) == set(expected_fields)

    def test_step_type_enum_values(self):
        step_type = USECASE_EXPORT_SCHEMA['properties']['steps']['items']['properties']['step_type']
        expected = ['navigation', 'validation', 'secret', 'retrieve_value', 'assertion', 'url', 'download']
        assert step_type['enum'] == expected

    def test_validation_type_allows_empty_string(self):
        vt = USECASE_EXPORT_SCHEMA['properties']['steps']['items']['properties']['validation_type']
        assert '' in vt['enum']
        assert 'string' in vt['enum']
        assert 'bool' in vt['enum']
        assert 'number' in vt['enum']

    def test_validation_operator_includes_all_operators(self):
        vo = USECASE_EXPORT_SCHEMA['properties']['steps']['items']['properties']['validation_operator']
        # String operators
        assert 'exact' in vo['enum']
        assert 'contains' in vo['enum']
        assert 'not_equal' in vo['enum']
        # Number operators
        assert 'equals' in vo['enum']
        assert 'less_then' in vo['enum']
        assert 'greater_then' in vo['enum']
        # Empty string for unused
        assert '' in vo['enum']

    def test_value_type_allows_empty_string(self):
        vt = USECASE_EXPORT_SCHEMA['properties']['steps']['items']['properties']['value_type']
        assert '' in vt['enum']
        assert 'string' in vt['enum']

    def test_variables_array_item_schema(self):
        var_item = USECASE_EXPORT_SCHEMA['properties']['variables']['items']
        assert 'key' in var_item['properties']
        assert 'value' in var_item['properties']
        assert var_item['additionalProperties'] is False

    def test_secrets_array_item_schema(self):
        sec_item = USECASE_EXPORT_SCHEMA['properties']['secrets']['items']
        assert 'key' in sec_item['properties']
        assert 'description' in sec_item['properties']

    def test_hooks_is_null_type(self):
        hooks = USECASE_EXPORT_SCHEMA['properties']['hooks']
        assert hooks['type'] == 'null'

    def test_step_additionalProperties_false(self):
        step = USECASE_EXPORT_SCHEMA['properties']['steps']['items']
        assert step['additionalProperties'] is False


# --- _get_tool_config tests ---

class TestGetToolConfig:
    """Tests for _get_tool_config helper."""

    def test_returns_correct_structure(self):
        config = _get_tool_config()
        assert 'tools' in config
        assert 'toolChoice' in config
        assert len(config['tools']) == 1

    def test_tool_spec_fields(self):
        config = _get_tool_config()
        tool_spec = config['tools'][0]['toolSpec']
        assert tool_spec['name'] == 'usecase_export'
        assert 'description' in tool_spec
        assert 'inputSchema' in tool_spec

    def test_tool_choice_forces_usecase_export(self):
        config = _get_tool_config()
        assert config['toolChoice'] == {'tool': {'name': 'usecase_export'}}

    def test_input_schema_matches_module_schema(self):
        config = _get_tool_config()
        input_schema = config['tools'][0]['toolSpec']['inputSchema']['json']
        assert input_schema == USECASE_EXPORT_SCHEMA

    def test_input_schema_is_dict_not_string(self):
        """The inputSchema json field must be a dict, not a JSON string."""
        config = _get_tool_config()
        input_schema = config['tools'][0]['toolSpec']['inputSchema']['json']
        assert isinstance(input_schema, dict)
        assert input_schema['type'] == 'object'


# --- create_prompt tests (no inline JSON example) ---

class TestCreatePromptNoInlineJson:
    """Tests that create_prompt no longer embeds a concrete JSON example."""

    def test_no_concrete_json_example(self):
        """Prompt should not contain the old inline JSON with actual values."""
        prompt = create_prompt('Test', 'https://example.com', 'Navigate to the page and verify the heading is visible on the screen', 'us-east-1')
        assert '"steps": [' not in prompt
        assert '"sort": 1,' not in prompt

    def test_prompt_references_schema_enforcement(self):
        """Prompt should mention that schema is enforced by the system."""
        prompt = create_prompt('Test', 'https://example.com', 'Navigate to the page and verify the heading is visible on the screen', 'us-east-1')
        assert 'schema' in prompt.lower()

    def test_prompt_still_contains_field_values(self):
        """Prompt should still tell the model what values to use for top-level fields."""
        prompt = create_prompt('My Test', 'https://example.com', 'Navigate to the page and verify the heading is visible on the screen', 'us-east-1')
        assert 'exportVersion: "1.0"' in prompt
        assert 'usecase.name: "My Test"' in prompt
        assert 'usecase.starting_url: "https://example.com"' in prompt
        assert 'usecase.executing_region: "us-east-1"' in prompt

    def test_prompt_still_contains_step_type_guidelines(self):
        prompt = create_prompt('Test', 'https://example.com', 'Navigate to the page and verify the heading is visible on the screen', 'us-east-1')
        assert 'navigation' in prompt
        assert 'validation' in prompt
        assert 'retrieve_value' in prompt
        assert 'assertion' in prompt

    def test_prompt_still_contains_critical_requirements(self):
        prompt = create_prompt('Test', 'https://example.com', 'Check the page loads correctly and shows the expected content', 'us-east-1')
        assert 'CRITICAL REQUIREMENTS' in prompt
        assert 'FIRST step' in prompt

    def test_prompt_contains_semantic_over_mechanical_principle(self):
        """Prompt should instruct the model to generate goal-oriented steps for complex widgets."""
        prompt = create_prompt('Test', 'https://example.com', 'Check the page loads correctly and shows the expected content', 'us-east-1')
        assert 'SEMANTIC OVER MECHANICAL' in prompt
        assert 'date picker' in prompt.lower()
        assert 'WHAT to achieve' in prompt

    def test_validation_instructions_ask_for_content_not_visibility(self):
        """Validation instructions must ask for actual content, not visibility booleans."""
        prompt = create_prompt('Test', 'https://example.com', 'Check the page loads correctly and shows the expected content', 'us-east-1')
        assert 'return the value of the main page heading' in prompt
        assert 'NEVER ask whether something "is visible"' in prompt
        assert 'NEVER ask about visibility' in prompt
        assert 'return the value of ...' in prompt


# --- invoke_bedrock tests ---

class TestInvokeBedrockToolConfig:
    """Tests for invoke_bedrock with tool-based structured output."""

    def _make_tool_use_response(self, tool_input):
        """Build a Bedrock Converse response with a toolUse block."""
        return {
            'output': {
                'message': {
                    'content': [{
                        'toolUse': {
                            'toolUseId': 'tooluse_test123',
                            'name': 'usecase_export',
                            'input': tool_input,
                        }
                    }]
                }
            }
        }

    def _make_reasoning_plus_tool_response(self, tool_input):
        """Build a response with reasoningContent block followed by toolUse block."""
        return {
            'output': {
                'message': {
                    'content': [
                        {
                            'reasoningContent': {
                                'reasoningText': {
                                    'text': '[REDACTED]',
                                }
                            }
                        },
                        {
                            'toolUse': {
                                'toolUseId': 'tooluse_test456',
                                'name': 'usecase_export',
                                'input': tool_input,
                            }
                        },
                    ]
                }
            }
        }

    @patch('generate_usecase.bedrock_runtime')
    def test_passes_tool_config(self, mock_bedrock):
        """invoke_bedrock should pass toolConfig to converse()."""
        mock_bedrock.converse.return_value = self._make_tool_use_response(
            {'exportVersion': '1.0', 'steps': []}
        )
        invoke_bedrock('Test', 'https://example.com', 'Navigate to the page and verify the heading is visible on the screen', 'us-east-1', 'test-model')

        call_kwargs = mock_bedrock.converse.call_args[1]
        assert 'toolConfig' in call_kwargs
        assert 'outputConfig' not in call_kwargs
        tool_config = call_kwargs['toolConfig']
        assert tool_config['toolChoice'] == {'tool': {'name': 'usecase_export'}}
        assert len(tool_config['tools']) == 1

    @patch('generate_usecase.bedrock_runtime')
    def test_returns_json_from_tool_use_response(self, mock_bedrock):
        """Should return JSON serialized from the toolUse input dict."""
        tool_input = {
            'exportVersion': '1.0',
            'exportedAt': '2026-03-15T00:00:00Z',
            'usecase': {'name': 'Test'},
            'steps': [],
            'variables': [],
            'secrets': [],
            'hooks': None,
        }
        mock_bedrock.converse.return_value = self._make_tool_use_response(tool_input)
        result = invoke_bedrock('Test', 'https://example.com', 'Navigate to the page and verify the heading is visible on the screen', 'us-east-1', 'test-model')
        parsed = json.loads(result)
        assert parsed['exportVersion'] == '1.0'
        assert parsed['usecase']['name'] == 'Test'

    @patch('generate_usecase.bedrock_runtime')
    def test_non_nova2_model_uses_inference_config(self, mock_bedrock):
        """Non-Nova 2 models should use inferenceConfig with maxTokens and temperature."""
        mock_bedrock.converse.return_value = self._make_tool_use_response(
            {'exportVersion': '1.0'}
        )
        invoke_bedrock('Test', 'https://example.com', 'Navigate to the page and verify the heading is visible on the screen', 'us-east-1', 'test-model')

        call_kwargs = mock_bedrock.converse.call_args[1]
        assert 'inferenceConfig' in call_kwargs
        assert call_kwargs['inferenceConfig']['maxTokens'] == 8192
        assert call_kwargs['inferenceConfig']['temperature'] == 0.1
        assert 'additionalModelRequestFields' not in call_kwargs

    @patch('generate_usecase.bedrock_runtime')
    def test_nova2_model_uses_extended_thinking(self, mock_bedrock):
        """Nova 2 models should use additionalModelRequestFields with reasoningConfig."""
        mock_bedrock.converse.return_value = self._make_tool_use_response(
            {'exportVersion': '1.0'}
        )
        invoke_bedrock('Test', 'https://example.com', 'Navigate to the page and verify the heading is visible on the screen', 'us-east-1', 'us.amazon.nova-2-lite-v1:0')

        call_kwargs = mock_bedrock.converse.call_args[1]
        assert 'additionalModelRequestFields' in call_kwargs
        reasoning_config = call_kwargs['additionalModelRequestFields']['reasoningConfig']
        assert reasoning_config['type'] == 'enabled'
        assert reasoning_config['maxReasoningEffort'] == 'low'
        # Medium effort: inferenceConfig is set with maxTokens and temperature
        assert 'inferenceConfig' in call_kwargs
        assert call_kwargs['inferenceConfig']['maxTokens'] == 40000
        assert call_kwargs['inferenceConfig']['temperature'] == 0

    @patch('generate_usecase.bedrock_runtime')
    def test_nova2_skips_reasoning_content_blocks(self, mock_bedrock):
        """Should skip reasoningContent blocks and extract toolUse block."""
        tool_input = {
            'exportVersion': '1.0',
            'usecase': {'name': 'Test'},
            'steps': [],
        }
        mock_bedrock.converse.return_value = self._make_reasoning_plus_tool_response(tool_input)
        result = invoke_bedrock('Test', 'https://example.com', 'Navigate to the page and verify the heading is visible on the screen', 'us-east-1', 'us.amazon.nova-2-lite-v1:0')
        parsed = json.loads(result)
        assert parsed['exportVersion'] == '1.0'
        assert parsed['usecase']['name'] == 'Test'

    @patch('generate_usecase.bedrock_runtime')
    def test_raises_on_empty_content(self, mock_bedrock):
        mock_bedrock.converse.return_value = {
            'output': {'message': {'content': []}}
        }
        with pytest.raises(Exception, match='no content'):
            invoke_bedrock('Test', 'https://example.com', 'Navigate to the page and verify the heading is visible on the screen', 'us-east-1', 'test-model')

    @patch('generate_usecase.bedrock_runtime')
    def test_fallback_to_text_block(self, mock_bedrock):
        """If no toolUse block, should fall back to extracting from text."""
        mock_bedrock.converse.return_value = {
            'output': {
                'message': {
                    'content': [{'text': '{"exportVersion": "1.0", "steps": []}'}]
                }
            }
        }
        result = invoke_bedrock('Test', 'https://example.com', 'Navigate to the page and verify the heading is visible on the screen', 'us-east-1', 'test-model')
        parsed = json.loads(result)
        assert parsed['exportVersion'] == '1.0'

    @patch('generate_usecase.bedrock_runtime')
    def test_fallback_skips_reasoning_blocks_for_text(self, mock_bedrock):
        """Fallback text extraction should skip reasoningContent blocks."""
        mock_bedrock.converse.return_value = {
            'output': {
                'message': {
                    'content': [
                        {'reasoningContent': {'reasoningText': {'text': '[REDACTED]'}}},
                        {'text': '{"exportVersion": "1.0", "steps": []}'},
                    ]
                }
            }
        }
        result = invoke_bedrock('Test', 'https://example.com', 'Navigate to the page and verify the heading is visible on the screen', 'us-east-1', 'us.amazon.nova-2-lite-v1:0')
        parsed = json.loads(result)
        assert parsed['exportVersion'] == '1.0'

    @patch('generate_usecase.bedrock_runtime')
    def test_raises_on_no_tool_use_and_empty_text(self, mock_bedrock):
        """No toolUse block and empty text should raise."""
        mock_bedrock.converse.return_value = {
            'output': {'message': {'content': [{'text': ''}]}}
        }
        with pytest.raises(Exception, match='no toolUse or text block'):
            invoke_bedrock('Test', 'https://example.com', 'Navigate to the page and verify the heading is visible on the screen', 'us-east-1', 'test-model')

    @patch('generate_usecase.bedrock_runtime')
    def test_raises_on_bedrock_error(self, mock_bedrock):
        mock_bedrock.converse.side_effect = Exception('ThrottlingException')
        with pytest.raises(Exception, match='ThrottlingException'):
            invoke_bedrock('Test', 'https://example.com', 'Navigate to the page and verify the heading is visible on the screen', 'us-east-1', 'test-model')

    @patch('generate_usecase.bedrock_runtime')
    def test_multimodal_path_also_passes_tool_config(self, mock_bedrock):
        """When screenshots are provided, toolConfig should still be passed."""
        from recording_models import (
            ActionEntry, RecordingSession, CDPRecordingPayload, RecordingData,
        )
        actions = [
            ActionEntry(
                id='act-1', type='click', prompt='Click button',
                url='https://example.com', timestamp=1000,
            ),
        ]
        session = RecordingSession(
            id='sess-1', startedAt=1000, stoppedAt=2000, tabId=1,
            startingUrl='https://example.com', actions=actions,
        )
        payload = CDPRecordingPayload(session=session, event_count=1, duration_seconds=1.0)
        recording = RecordingData(
            type='cdp_actions', version='1.0',
            data=payload.model_dump(), captured_at='2026-03-15T00:00:00+00:00',
        )
        screenshots = {'act-1': b'\xff\xd8\xff\xe0fake-jpeg'}

        mock_bedrock.converse.return_value = self._make_tool_use_response(
            {'exportVersion': '1.0'}
        )
        invoke_bedrock(
            'Test', 'https://example.com', 'Navigate to the page and verify the heading is visible on the screen',
            'us-east-1', 'test-model',
            recording_data=recording, screenshots=screenshots,
        )

        call_kwargs = mock_bedrock.converse.call_args[1]
        assert 'toolConfig' in call_kwargs
        assert 'outputConfig' not in call_kwargs
        assert call_kwargs['toolConfig']['toolChoice'] == {'tool': {'name': 'usecase_export'}}


# --- _is_nova2_model tests ---

class TestIsNova2Model:
    """Tests for _is_nova2_model helper."""

    def test_nova2_lite_detected(self):
        assert _is_nova2_model('us.amazon.nova-2-lite-v1:0') is True

    def test_nova2_pro_detected(self):
        assert _is_nova2_model('us.amazon.nova-2-pro-v1:0') is True

    def test_nova_pro_v1_not_detected(self):
        assert _is_nova2_model('us.amazon.nova-pro-v1:0') is False

    def test_qwen_not_detected(self):
        assert _is_nova2_model('qwen.qwen3-vl-235b-a22b') is False

    def test_claude_not_detected(self):
        assert _is_nova2_model('anthropic.claude-sonnet-4-v1:0') is False

    def test_case_insensitive(self):
        assert _is_nova2_model('us.amazon.NOVA-2-LITE-v1:0') is True
