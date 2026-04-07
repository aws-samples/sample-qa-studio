"""Unit tests for optional user journey when recording data is provided.

Tests cover:
- create_prompt: handles empty user_journey when recording_data is present
- handler: validates user_journey is optional when recording_data is present
- handler: still requires user_journey when no recording_data
"""
import json
import os
import pytest
from unittest.mock import patch, MagicMock

os.environ.setdefault('TABLE_NAME', 'test-table')
os.environ.setdefault('BUCKET_NAME', 'test-bucket')
os.environ.setdefault('BEDROCK_MODEL_ID', 'test-model')

from generate_usecase import create_prompt, handler
from recording_models import (
    ActionEntry,
    RecordingSession,
    CDPRecordingPayload,
    RecordingData,
)


# --- Fixtures ---

def _make_recording_data():
    """Build a valid RecordingData object."""
    actions = [
        ActionEntry(
            id='act-1', type='click', prompt='Click login button',
            url='https://example.com', timestamp=1000, isIntent=False, assertions=[],
        ),
        ActionEntry(
            id='act-2', type='type', prompt='Type username',
            url='https://example.com', timestamp=2000, isIntent=False, assertions=[],
        ),
    ]
    session = RecordingSession(
        id='sess-1', startedAt=1000, stoppedAt=5000, tabId=1,
        startingUrl='https://example.com', actions=actions,
    )
    payload = CDPRecordingPayload(
        session=session, event_count=2, duration_seconds=4.0,
    )
    return RecordingData(
        type='cdp_actions', version='1.0',
        data=payload.model_dump(), captured_at='2026-03-15T00:00:00+00:00',
    )


def _make_event(body: dict, scopes: list[str] | None = None) -> dict:
    """Build a minimal API Gateway event for the handler."""
    if scopes is None:
        scopes = ['api/usecases.write']
    return {
        'body': json.dumps(body),
        'requestContext': {
            'requestId': 'test-req-1',
            'authorizer': {
                'claims': {
                    'scope': ' '.join(scopes),
                    'email': 'test@example.com',
                },
            },
        },
    }


# --- create_prompt tests ---

class TestCreatePromptOptionalJourney:
    """Tests for create_prompt with empty user_journey."""

    def test_prompt_with_journey_and_recording(self):
        """Both journey text and recording data present."""
        recording = _make_recording_data()
        prompt = create_prompt('Login Test', 'https://example.com',
                               'User logs in with valid credentials and sees the dashboard',
                               'us-east-1', recording_data=recording)
        assert 'User logs in with valid credentials' in prompt
        assert 'RECORDED BROWSER INTERACTION' in prompt

    def test_prompt_with_journey_no_recording(self):
        """Journey text only, no recording — existing behavior."""
        prompt = create_prompt('Login Test', 'https://example.com',
                               'User logs in with valid credentials and sees the dashboard',
                               'us-east-1')
        assert 'User logs in with valid credentials' in prompt
        assert 'RECORDED BROWSER INTERACTION' not in prompt

    def test_prompt_with_recording_no_journey(self):
        """Recording data only, empty journey text."""
        recording = _make_recording_data()
        prompt = create_prompt('Login Test', 'https://example.com', '',
                               'us-east-1', recording_data=recording)
        assert 'derived from browser recording below' in prompt
        assert 'Generated from browser recording for' in prompt
        assert 'RECORDED BROWSER INTERACTION' in prompt

    def test_prompt_with_recording_whitespace_journey(self):
        """Recording data with whitespace-only journey text."""
        recording = _make_recording_data()
        prompt = create_prompt('Login Test', 'https://example.com', '   ',
                               'us-east-1', recording_data=recording)
        assert 'derived from browser recording below' in prompt

    def test_prompt_description_field_with_recording_only(self):
        """The JSON description field should reference recording, not empty journey."""
        recording = _make_recording_data()
        prompt = create_prompt('Login Test', 'https://example.com', '',
                               'us-east-1', recording_data=recording)
        assert 'Generated from browser recording for Login Test' in prompt
        # Should NOT have empty "Generated from user journey: "
        assert 'Generated from user journey: "' not in prompt


# --- handler tests ---

class TestHandlerOptionalJourney:
    """Tests for handler with optional user journey."""

    def test_handler_rejects_empty_journey_without_recording(self):
        """No journey and no recording → 400 validation error."""
        event = _make_event({
            'title': 'Login Test',
            'starting_url': 'https://example.com',
            'userJourney': '',
            'region': 'us-east-1',
        })
        response = handler(event, {})
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert not body['success']
        assert 'required' in body['error'].lower() or 'required' in str(body.get('details', '')).lower()

    @patch('generate_usecase.invoke_bedrock')
    @patch('generate_usecase.sanitize_and_fix_json')
    @patch('generate_usecase.validate_generated_json')
    def test_handler_accepts_empty_journey_with_recording(self, mock_validate, mock_sanitize, mock_bedrock):
        """Empty journey + valid recording → should pass validation and call Bedrock."""
        mock_bedrock.return_value = '{"exportVersion": "1.0"}'
        mock_sanitize.return_value = '{"exportVersion": "1.0"}'
        mock_validate.return_value = (True, [], {'exportVersion': '1.0', 'steps': []})

        recording = _make_recording_data()
        event = _make_event({
            'title': 'Login Test',
            'starting_url': 'https://example.com',
            'userJourney': '',
            'region': 'us-east-1',
            'recording_data': recording.model_dump(),
        })
        response = handler(event, {})
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['success']
        mock_bedrock.assert_called_once()

    @patch('generate_usecase.invoke_bedrock')
    @patch('generate_usecase.sanitize_and_fix_json')
    @patch('generate_usecase.validate_generated_json')
    def test_handler_accepts_journey_with_recording(self, mock_validate, mock_sanitize, mock_bedrock):
        """Both journey and recording present → should pass validation."""
        mock_bedrock.return_value = '{"exportVersion": "1.0"}'
        mock_sanitize.return_value = '{"exportVersion": "1.0"}'
        mock_validate.return_value = (True, [], {'exportVersion': '1.0', 'steps': []})

        recording = _make_recording_data()
        event = _make_event({
            'title': 'Login Test',
            'starting_url': 'https://example.com',
            'userJourney': 'User navigates to the login page and enters their credentials to access the dashboard successfully',
            'region': 'us-east-1',
            'recording_data': recording.model_dump(),
        })
        response = handler(event, {})
        assert response['statusCode'] == 200

    def test_handler_rejects_short_journey_without_recording(self):
        """Short journey (< 50 chars) without recording → 400."""
        event = _make_event({
            'title': 'Login Test',
            'starting_url': 'https://example.com',
            'userJourney': 'Short text',
            'region': 'us-east-1',
        })
        response = handler(event, {})
        assert response['statusCode'] == 400

    @patch('generate_usecase.invoke_bedrock')
    @patch('generate_usecase.sanitize_and_fix_json')
    @patch('generate_usecase.validate_generated_json')
    def test_handler_accepts_empty_journey_with_malformed_recording_falls_back(self, mock_validate, mock_sanitize, mock_bedrock):
        """Empty journey + malformed recording → recording ignored → 400 (no journey, no valid recording)."""
        event = _make_event({
            'title': 'Login Test',
            'starting_url': 'https://example.com',
            'userJourney': '',
            'region': 'us-east-1',
            'recording_data': {'bad': 'data'},
        })
        response = handler(event, {})
        # Malformed recording_data is ignored, so no recording_data and no journey → 400
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'required' in body['error'].lower()
