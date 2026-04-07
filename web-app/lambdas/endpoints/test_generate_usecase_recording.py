"""Unit tests for recording section builder functions in generate_usecase.py.

Tests cover:
- _format_action_line: variable annotations for extract_variable and paste actions
- _build_variable_instructions: conditional instruction generation
- _build_recording_section: full section with variable context
- _build_recording_content_blocks: multimodal blocks with variable context
"""
import os
import pytest

os.environ.setdefault('TABLE_NAME', 'test-table')
os.environ.setdefault('BUCKET_NAME', 'test-bucket')

from generate_usecase import (
    _format_action_line,
    _build_variable_instructions,
    _build_recording_section,
    _build_recording_content_blocks,
)
from recording_models import (
    ActionEntry,
    Assertion,
    RecordingSession,
    CDPRecordingPayload,
    RecordingData,
)


# --- Fixtures ---

def _make_action(type='click', prompt='Click button', url='https://example.com',
                 variable_name=None, selected_text=None, source_variable_name=None,
                 action_id='act-1', assertions=None):
    """Build an ActionEntry with optional variable fields."""
    return ActionEntry(
        id=action_id,
        type=type,
        prompt=prompt,
        url=url,
        timestamp=1000,
        isIntent=False,
        assertions=assertions or [],
        variableName=variable_name,
        selectedText=selected_text,
        sourceVariableName=source_variable_name,
    )


def _make_recording_data(actions):
    """Wrap a list of ActionEntry instances into a RecordingData envelope."""
    session = RecordingSession(
        id='sess-1',
        startedAt=1000,
        stoppedAt=2000,
        tabId=1,
        startingUrl='https://example.com',
        actions=actions,
    )
    payload = CDPRecordingPayload(
        session=session,
        event_count=len(actions),
        duration_seconds=1.0,
    )
    return RecordingData(
        type='cdp_actions',
        version='1.0',
        data=payload.model_dump(),
        captured_at='2026-03-15T00:00:00+00:00',
    )


# --- _format_action_line tests ---

class TestFormatActionLine:
    """Tests for _format_action_line."""

    def test_plain_click_action(self):
        action = _make_action(type='click', prompt='Click the submit button')
        result = _format_action_line(1, action)
        assert result == '1. [click] Click the submit button (URL: https://example.com)'

    def test_extract_variable_with_name_and_text(self):
        action = _make_action(
            type='extract_variable',
            prompt='Extract the cart count',
            variable_name='var_1',
            selected_text='5',
        )
        result = _format_action_line(3, action)
        assert '[captures → {{var_1}}' in result
        assert 'value: "5"' in result
        assert '(URL: https://example.com)' in result

    def test_extract_variable_without_selected_text(self):
        action = _make_action(
            type='extract_variable',
            prompt='Extract the heading',
            variable_name='var_2',
            selected_text=None,
        )
        result = _format_action_line(1, action)
        assert '[captures → {{var_2}}]' in result
        assert 'value:' not in result

    def test_extract_variable_without_variable_name(self):
        """extract_variable with no variableName should not get annotation."""
        action = _make_action(
            type='extract_variable',
            prompt='Extract something',
            variable_name=None,
        )
        result = _format_action_line(1, action)
        assert 'captures' not in result

    def test_paste_with_source_variable(self):
        action = _make_action(
            type='paste',
            prompt='Paste into search field',
            source_variable_name='var_1',
        )
        result = _format_action_line(2, action)
        assert '[uses → {{var_1}}]' in result

    def test_paste_without_source_variable(self):
        """paste without sourceVariableName should not get annotation."""
        action = _make_action(
            type='paste',
            prompt='Paste text',
            source_variable_name=None,
        )
        result = _format_action_line(1, action)
        assert 'uses' not in result

    def test_navigation_action_no_annotations(self):
        action = _make_action(type='navigation', prompt='Navigate to page')
        result = _format_action_line(5, action)
        assert result == '5. [navigation] Navigate to page (URL: https://example.com)'
        assert 'captures' not in result
        assert 'uses' not in result

    def test_action_without_url(self):
        action = _make_action(type='scroll', prompt='Scroll down', url='')
        result = _format_action_line(1, action)
        assert 'URL:' not in result


# --- _build_variable_instructions tests ---

class TestBuildVariableInstructions:
    """Tests for _build_variable_instructions."""

    def test_no_variable_actions_returns_empty(self):
        actions = [
            _make_action(type='click', prompt='Click'),
            _make_action(type='type', prompt='Type text'),
        ]
        result = _build_variable_instructions(actions)
        assert result == ''

    def test_extract_only_includes_retrieve_value_instruction(self):
        actions = [
            _make_action(type='extract_variable', prompt='Extract', variable_name='var_1'),
        ]
        result = _build_variable_instructions(actions)
        assert 'VARIABLE MAPPING INSTRUCTIONS' in result
        assert 'retrieve_value' in result
        assert 'capture_variable' in result

    def test_paste_only_includes_navigation_instruction(self):
        actions = [
            _make_action(type='paste', prompt='Paste', source_variable_name='var_1'),
        ]
        result = _build_variable_instructions(actions)
        assert 'VARIABLE MAPPING INSTRUCTIONS' in result
        assert '{{VariableName}}' in result

    def test_both_extract_and_paste(self):
        actions = [
            _make_action(type='extract_variable', prompt='Extract', variable_name='var_1'),
            _make_action(type='click', prompt='Click button', action_id='act-2'),
            _make_action(type='paste', prompt='Paste', source_variable_name='var_1', action_id='act-3'),
        ]
        result = _build_variable_instructions(actions)
        assert 'retrieve_value' in result
        assert '{{VariableName}}' in result
        assert 'assertion' in result

    def test_extract_without_variable_name_ignored(self):
        """extract_variable with no variableName should not trigger instructions."""
        actions = [
            _make_action(type='extract_variable', prompt='Extract', variable_name=None),
        ]
        result = _build_variable_instructions(actions)
        assert result == ''

    def test_paste_without_source_variable_ignored(self):
        """paste with no sourceVariableName should not trigger instructions."""
        actions = [
            _make_action(type='paste', prompt='Paste', source_variable_name=None),
        ]
        result = _build_variable_instructions(actions)
        assert result == ''

    def test_runtime_vs_static_variable_distinction(self):
        """Instructions should clarify that captured variables are runtime, not static."""
        actions = [
            _make_action(type='extract_variable', prompt='Extract', variable_name='var_1'),
        ]
        result = _build_variable_instructions(actions)
        assert 'variables' in result.lower()
        assert 'runtime' in result.lower()

    def test_paste_mentions_flexible_interaction(self):
        """Paste instructions should allow non-typing interactions (e.g., date picker)."""
        actions = [
            _make_action(type='paste', prompt='Paste DOB', source_variable_name='var_1'),
        ]
        result = _build_variable_instructions(actions)
        assert 'date picker' in result.lower()
        assert 'dropdown' in result.lower()
        # Should describe goal-oriented instructions, not micro-steps
        assert 'goal' in result.lower()

    def test_proactive_retrieve_value_encouraged(self):
        """Instructions should encourage additional retrieve_value beyond explicit extracts."""
        actions = [
            _make_action(type='extract_variable', prompt='Extract', variable_name='var_1'),
        ]
        result = _build_variable_instructions(actions)
        assert 'additional retrieve_value' in result.lower() or 'may also generate' in result.lower()


# --- _build_recording_section tests ---

class TestBuildRecordingSection:
    """Tests for _build_recording_section with variable annotations."""

    def test_empty_actions_returns_empty(self):
        recording_data = _make_recording_data([])
        result = _build_recording_section(recording_data)
        assert result == ''

    def test_plain_actions_no_variable_instructions(self):
        actions = [
            _make_action(type='click', prompt='Click login'),
            _make_action(type='type', prompt='Type username', action_id='act-2'),
        ]
        recording_data = _make_recording_data(actions)
        result = _build_recording_section(recording_data)
        assert 'RECORDED BROWSER INTERACTION SEQUENCE' in result
        assert '[click] Click login' in result
        assert '[type] Type username' in result
        assert 'VARIABLE MAPPING INSTRUCTIONS' not in result

    def test_extract_and_paste_includes_annotations_and_instructions(self):
        actions = [
            _make_action(
                type='extract_variable', prompt='Extract cart count',
                variable_name='var_1', selected_text='3', action_id='act-1',
            ),
            _make_action(type='click', prompt='Click checkout', action_id='act-2'),
            _make_action(
                type='paste', prompt='Paste into quantity',
                source_variable_name='var_1', action_id='act-3',
            ),
        ]
        recording_data = _make_recording_data(actions)
        result = _build_recording_section(recording_data)

        # Variable annotations present
        assert '[captures → {{var_1}}, value: "3"]' in result
        assert '[uses → {{var_1}}]' in result

        # Variable mapping instructions appended
        assert 'VARIABLE MAPPING INSTRUCTIONS' in result
        assert 'retrieve_value' in result

    def test_invalid_recording_data_returns_empty(self):
        """Malformed data should not raise, just return empty string."""
        bad_data = RecordingData(
            type='cdp_actions',
            version='1.0',
            data={'invalid': 'structure'},
            captured_at='2026-03-15T00:00:00+00:00',
        )
        result = _build_recording_section(bad_data)
        assert result == ''


# --- _build_recording_content_blocks tests ---

class TestBuildRecordingContentBlocks:
    """Tests for _build_recording_content_blocks with variable annotations."""

    def test_empty_actions_returns_empty_list(self):
        recording_data = _make_recording_data([])
        result = _build_recording_content_blocks(recording_data)
        assert result == []

    def test_plain_actions_no_variable_instructions(self):
        actions = [
            _make_action(type='click', prompt='Click button'),
        ]
        recording_data = _make_recording_data(actions)
        blocks = _build_recording_content_blocks(recording_data)

        text_blocks = [b['text'] for b in blocks if 'text' in b]
        full_text = '\n'.join(text_blocks)
        assert '[click] Click button' in full_text
        assert 'VARIABLE MAPPING INSTRUCTIONS' not in full_text

    def test_extract_paste_includes_annotations_and_instructions(self):
        actions = [
            _make_action(
                type='extract_variable', prompt='Extract price',
                variable_name='var_1', selected_text='$9.99', action_id='act-1',
            ),
            _make_action(
                type='paste', prompt='Paste into coupon field',
                source_variable_name='var_1', action_id='act-2',
            ),
        ]
        recording_data = _make_recording_data(actions)
        blocks = _build_recording_content_blocks(recording_data)

        text_blocks = [b['text'] for b in blocks if 'text' in b]
        full_text = '\n'.join(text_blocks)

        assert '[captures → {{var_1}}' in full_text
        assert '[uses → {{var_1}}]' in full_text
        assert 'VARIABLE MAPPING INSTRUCTIONS' in full_text

    def test_screenshots_interleaved(self):
        actions = [
            _make_action(type='click', prompt='Click', action_id='act-1'),
            _make_action(type='type', prompt='Type', action_id='act-2'),
        ]
        recording_data = _make_recording_data(actions)
        screenshots = {'act-1': b'\xff\xd8\xff\xe0fake-jpeg'}

        blocks = _build_recording_content_blocks(recording_data, screenshots=screenshots)
        image_blocks = [b for b in blocks if 'image' in b]
        assert len(image_blocks) == 1
        assert image_blocks[0]['image']['format'] == 'jpeg'

    def test_invalid_recording_data_returns_empty_list(self):
        bad_data = RecordingData(
            type='cdp_actions',
            version='1.0',
            data={'invalid': 'structure'},
            captured_at='2026-03-15T00:00:00+00:00',
        )
        result = _build_recording_content_blocks(bad_data)
        assert result == []
