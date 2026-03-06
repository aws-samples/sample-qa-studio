"""
Unit tests for get_step_trace Lambda handler.

Tests the Lambda that fetches and parses JSON trace data for execution steps.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

import get_step_trace
from get_step_trace import (
    TraceStep,
    TraceMetadata,
    StepTraceResponse,
    parse_trace_json,
    find_trace_s3_key,
    handler,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_TRACE_STEP = {
    "request": {
        "screenshot": "data:image/jpeg;base64,abc123",
        "prompt": "Navigate to login page",
        "metadata": {},
    },
    "response": {
        "program": "agentClick('#login');",
        "rawProgramBody": 'think("Click the login button");\nagentClick(\'#login\');',
        "requestId": "req_001",
    },
    "screenshotWithBbox": "data:image/jpeg;base64,bbox_abc123",
}

SAMPLE_METADATA = {
    "session_id": "sess_abc",
    "act_id": "act_001",
    "num_steps_executed": 3,
    "start_time": 1700000000.0,
    "end_time": 1700000010.0,
    "prompt": "Navigate to login page",
    "step_server_times_s": [],
    "time_worked_s": 10.0,
    "human_wait_time_s": 0.0,
}

SAMPLE_TRACE_JSON = json.dumps({
    "steps": [SAMPLE_TRACE_STEP],
    "metadata": SAMPLE_METADATA,
})


@pytest.fixture
def mock_env_vars():
    """Mock environment variables."""
    with patch.dict(os.environ, {
        "DYNAMODB_TABLE_NAME": "test-table",
        "S3_BUCKET": "test-bucket",
    }):
        yield


@pytest.fixture
def valid_event():
    """Minimal valid API Gateway proxy event."""
    return {
        "pathParameters": {
            "id": "uc_123",
            "executionId": "exec_456",
            "stepId": "3",
        },
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": "user-1",
                    "scope": "api/executions.read",
                }
            }
        },
    }


def _make_step_item(sort_value, act_id=None, **extra):
    """Helper to build a DynamoDB step item returned by query."""
    item = {
        "pk": "EXECUTION#exec_456",
        "sk": "EXECUTION_STEP#some-uuid",
        "sort": sort_value,
    }
    if act_id is not None:
        item["act_id"] = act_id
    item.update(extra)
    return item


# ---------------------------------------------------------------------------
# Pydantic model tests
# ---------------------------------------------------------------------------

class TestTraceStep:
    def test_valid_trace_step(self):
        step = TraceStep(**SAMPLE_TRACE_STEP)
        assert step.request.screenshot == "data:image/jpeg;base64,abc123"
        assert step.response.rawProgramBody == 'think("Click the login button");\nagentClick(\'#login\');'
        assert step.screenshotWithBbox == "data:image/jpeg;base64,bbox_abc123"

    def test_all_optional_fields(self):
        step = TraceStep()
        assert step.request is None
        assert step.response is None
        assert step.screenshotWithBbox is None

    def test_partial_fields(self):
        step = TraceStep(request={"screenshot": "img"})
        assert step.request.screenshot == "img"
        assert step.response is None
        assert step.screenshotWithBbox is None


class TestTraceMetadata:
    def test_valid_metadata(self):
        meta = TraceMetadata(**SAMPLE_METADATA)
        assert meta.num_steps_executed == 3

    def test_all_optional(self):
        meta = TraceMetadata()
        assert meta.num_steps_executed is None


class TestStepTraceResponse:
    def test_valid_response(self):
        resp = StepTraceResponse(
            trace_steps=[TraceStep(**SAMPLE_TRACE_STEP)],
            metadata=TraceMetadata(**SAMPLE_METADATA),
        )
        assert len(resp.trace_steps) == 1
        assert resp.metadata.num_steps_executed == 3


# ---------------------------------------------------------------------------
# parse_trace_json tests
# ---------------------------------------------------------------------------

class TestParseTraceJson:
    def test_valid_json(self):
        result = parse_trace_json(SAMPLE_TRACE_JSON)
        assert isinstance(result, StepTraceResponse)
        assert len(result.trace_steps) == 1
        assert result.metadata.num_steps_executed == 3

    def test_invalid_json_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_trace_json("not json")

    def test_missing_steps_key_raises(self):
        data = json.dumps({"metadata": SAMPLE_METADATA})
        with pytest.raises(ValueError, match="Missing required top-level fields"):
            parse_trace_json(data)

    def test_missing_metadata_key_raises(self):
        data = json.dumps({"steps": [SAMPLE_TRACE_STEP]})
        with pytest.raises(ValueError, match="Missing required top-level fields"):
            parse_trace_json(data)

    def test_empty_object_raises(self):
        with pytest.raises(ValueError, match="Missing required top-level fields"):
            parse_trace_json("{}")

    def test_invalid_step_structure_does_not_raise(self):
        """Extra/unknown keys are ignored by pydantic — no error."""
        data = json.dumps({
            "steps": [{"bad": "data"}],
            "metadata": SAMPLE_METADATA,
        })
        result = parse_trace_json(data)
        assert len(result.trace_steps) == 1
        assert result.trace_steps[0].request is None

    def test_invalid_metadata_structure_does_not_raise(self):
        """Extra/unknown keys are ignored by pydantic — no error."""
        data = json.dumps({
            "steps": [SAMPLE_TRACE_STEP],
            "metadata": {"bad": "data"},
        })
        result = parse_trace_json(data)
        assert result.metadata.num_steps_executed is None

    def test_multiple_steps(self):
        step2 = {
            "request": {"screenshot": "data:image/jpeg;base64,step2"},
            "response": {"rawProgramBody": "think('step 2');"},
            "screenshotWithBbox": "data:image/jpeg;base64,bbox_step2",
        }
        data = json.dumps({
            "steps": [SAMPLE_TRACE_STEP, step2],
            "metadata": SAMPLE_METADATA,
        })
        result = parse_trace_json(data)
        assert len(result.trace_steps) == 2
        assert result.trace_steps[1].screenshotWithBbox == "data:image/jpeg;base64,bbox_step2"

    def test_screenshotWithBbox_included(self):
        result = parse_trace_json(SAMPLE_TRACE_JSON)
        assert result.trace_steps[0].screenshotWithBbox == "data:image/jpeg;base64,bbox_abc123"


# ---------------------------------------------------------------------------
# find_trace_s3_key tests
# ---------------------------------------------------------------------------

class TestFindTraceS3Key:
    def test_finds_matching_key(self):
        s3 = MagicMock()
        s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "uc/ex/sess/act_001_navigate_to_login_calls.json"},
            ]
        }
        result = find_trace_s3_key(s3, "bucket", "uc", "ex", "sess", "001")
        assert result == "uc/ex/sess/act_001_navigate_to_login_calls.json"

    def test_no_contents_returns_none(self):
        s3 = MagicMock()
        s3.list_objects_v2.return_value = {}
        result = find_trace_s3_key(s3, "bucket", "uc", "ex", "sess", "001")
        assert result is None

    def test_no_matching_key_returns_none(self):
        s3 = MagicMock()
        s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "uc/ex/sess/act_001_navigate.json"},  # no _calls.json suffix
            ]
        }
        result = find_trace_s3_key(s3, "bucket", "uc", "ex", "sess", "001")
        assert result is None

    def test_client_error_returns_none(self):
        s3 = MagicMock()
        s3.list_objects_v2.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "denied"}},
            "ListObjectsV2",
        )
        result = find_trace_s3_key(s3, "bucket", "uc", "ex", "sess", "001")
        assert result is None

    def test_correct_prefix_construction(self):
        s3 = MagicMock()
        s3.list_objects_v2.return_value = {}
        find_trace_s3_key(s3, "my-bucket", "uc_1", "ex_2", "sess_3", "act_4")
        s3.list_objects_v2.assert_called_once_with(
            Bucket="my-bucket",
            Prefix="uc_1/ex_2/sess_3/act_act_4",
        )

    def test_picks_first_matching_key(self):
        s3 = MagicMock()
        s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "uc/ex/sess/act_001_first_calls.json"},
                {"Key": "uc/ex/sess/act_001_second_calls.json"},
            ]
        }
        result = find_trace_s3_key(s3, "bucket", "uc", "ex", "sess", "001")
        assert result == "uc/ex/sess/act_001_first_calls.json"



# ---------------------------------------------------------------------------
# handler tests
# ---------------------------------------------------------------------------

class TestHandler:
    @patch("get_step_trace.require_scopes")
    def test_scope_validation_failure(self, mock_scopes, valid_event):
        error_resp = {"statusCode": 403, "body": "Forbidden"}
        mock_scopes.return_value = ({}, error_resp)
        result = handler(valid_event, None)
        assert result == error_resp

    @patch("get_step_trace.require_scopes")
    def test_missing_path_params(self, mock_scopes):
        mock_scopes.return_value = ({"identity": "user"}, None)
        event = {"pathParameters": {}}
        result = handler(event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 400
        assert "Missing required parameters" in body["error"]

    @patch("get_step_trace.require_scopes")
    def test_null_path_params(self, mock_scopes):
        mock_scopes.return_value = ({"identity": "user"}, None)
        event = {"pathParameters": None}
        result = handler(event, None)
        assert result["statusCode"] == 400

    @patch("get_step_trace.require_scopes")
    def test_missing_path_params_key(self, mock_scopes):
        mock_scopes.return_value = ({"identity": "user"}, None)
        event = {}
        result = handler(event, None)
        assert result["statusCode"] == 400

    @patch("get_step_trace.boto3")
    @patch("get_step_trace.require_scopes")
    def test_step_not_found(self, mock_scopes, mock_boto3, mock_env_vars, valid_event):
        mock_scopes.return_value = ({"identity": "user"}, None)
        table = MagicMock()
        # query returns no matching step items
        table.query.return_value = {"Items": []}
        mock_boto3.resource.return_value.Table.return_value = table

        result = handler(valid_event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 404
        assert "Execution step not found" in body["error"]

    @patch("get_step_trace.boto3")
    @patch("get_step_trace.require_scopes")
    def test_step_not_found_wrong_sort(self, mock_scopes, mock_boto3, mock_env_vars, valid_event):
        """Query returns steps but none match the requested sort value."""
        mock_scopes.return_value = ({"identity": "user"}, None)
        table = MagicMock()
        table.query.return_value = {"Items": [
            _make_step_item(sort_value=1, act_id="act_001"),
            _make_step_item(sort_value=2, act_id="act_002"),
        ]}
        mock_boto3.resource.return_value.Table.return_value = table

        result = handler(valid_event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 404
        assert "Execution step not found" in body["error"]

    @patch("get_step_trace.boto3")
    @patch("get_step_trace.require_scopes")
    def test_no_act_id(self, mock_scopes, mock_boto3, mock_env_vars, valid_event):
        mock_scopes.return_value = ({"identity": "user"}, None)
        table = MagicMock()
        # step found but has no act_id
        table.query.return_value = {"Items": [_make_step_item(sort_value=3)]}
        mock_boto3.resource.return_value.Table.return_value = table

        result = handler(valid_event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 404
        assert "No trace available" in body["error"]

    @patch("get_step_trace.boto3")
    @patch("get_step_trace.require_scopes")
    def test_cached_act_id(self, mock_scopes, mock_boto3, mock_env_vars, valid_event):
        mock_scopes.return_value = ({"identity": "user"}, None)
        table = MagicMock()
        table.query.return_value = {"Items": [_make_step_item(sort_value=3, act_id="cached")]}
        mock_boto3.resource.return_value.Table.return_value = table

        result = handler(valid_event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 404
        assert "cached step" in body["error"]

    @patch("get_step_trace.boto3")
    @patch("get_step_trace.require_scopes")
    def test_error_act_id(self, mock_scopes, mock_boto3, mock_env_vars, valid_event):
        mock_scopes.return_value = ({"identity": "user"}, None)
        table = MagicMock()
        table.query.return_value = {"Items": [_make_step_item(sort_value=3, act_id="error")]}
        mock_boto3.resource.return_value.Table.return_value = table

        result = handler(valid_event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 404
        assert "errored step" in body["error"]

    @patch("get_step_trace.boto3")
    @patch("get_step_trace.require_scopes")
    def test_execution_not_found(self, mock_scopes, mock_boto3, mock_env_vars, valid_event):
        mock_scopes.return_value = ({"identity": "user"}, None)
        table = MagicMock()
        # step query succeeds, execution get_item returns nothing
        table.query.return_value = {"Items": [_make_step_item(sort_value=3, act_id="act_001")]}
        table.get_item.return_value = {}
        mock_boto3.resource.return_value.Table.return_value = table

        result = handler(valid_event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 404
        assert "Execution not found" in body["error"]

    @patch("get_step_trace.boto3")
    @patch("get_step_trace.require_scopes")
    def test_no_session_id(self, mock_scopes, mock_boto3, mock_env_vars, valid_event):
        mock_scopes.return_value = ({"identity": "user"}, None)
        table = MagicMock()
        table.query.return_value = {"Items": [_make_step_item(sort_value=3, act_id="act_001")]}
        table.get_item.return_value = {"Item": {"pk": "x"}}  # no nova_session_id
        mock_boto3.resource.return_value.Table.return_value = table

        result = handler(valid_event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 404
        assert "no session ID" in body["error"]

    @patch("get_step_trace.find_trace_s3_key", return_value=None)
    @patch("get_step_trace.boto3")
    @patch("get_step_trace.require_scopes")
    def test_trace_file_not_found(self, mock_scopes, mock_boto3, mock_find, mock_env_vars, valid_event):
        mock_scopes.return_value = ({"identity": "user"}, None)
        table = MagicMock()
        table.query.return_value = {"Items": [_make_step_item(sort_value=3, act_id="act_001")]}
        table.get_item.return_value = {"Item": {"nova_session_id": "sess_abc"}}
        mock_boto3.resource.return_value.Table.return_value = table

        result = handler(valid_event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 404
        assert "Trace file not found" in body["error"]

    @patch("get_step_trace.parse_trace_json")
    @patch("get_step_trace.find_trace_s3_key", return_value="uc/ex/sess/act_001_nav_calls.json")
    @patch("get_step_trace.boto3")
    @patch("get_step_trace.require_scopes")
    def test_successful_trace_retrieval(self, mock_scopes, mock_boto3, mock_find, mock_parse, mock_env_vars, valid_event):
        mock_scopes.return_value = ({"identity": "user"}, None)
        table = MagicMock()
        table.query.return_value = {"Items": [_make_step_item(sort_value=3, act_id="act_001")]}
        table.get_item.return_value = {"Item": {"nova_session_id": "sess_abc"}}
        mock_boto3.resource.return_value.Table.return_value = table

        s3_client = MagicMock()
        body_mock = MagicMock()
        body_mock.read.return_value = SAMPLE_TRACE_JSON.encode("utf-8")
        s3_client.get_object.return_value = {"Body": body_mock}
        mock_boto3.client.return_value = s3_client

        trace_resp = StepTraceResponse(
            trace_steps=[TraceStep(**SAMPLE_TRACE_STEP)],
            metadata=TraceMetadata(**SAMPLE_METADATA),
        )
        mock_parse.return_value = trace_resp

        result = handler(valid_event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert "trace_steps" in body
        assert "metadata" in body
        assert body["metadata"]["num_steps_executed"] == 3

    @patch("get_step_trace.find_trace_s3_key", return_value="uc/ex/sess/act_001_nav_calls.json")
    @patch("get_step_trace.boto3")
    @patch("get_step_trace.require_scopes")
    def test_s3_get_object_no_such_key(self, mock_scopes, mock_boto3, mock_find, mock_env_vars, valid_event):
        mock_scopes.return_value = ({"identity": "user"}, None)
        table = MagicMock()
        table.query.return_value = {"Items": [_make_step_item(sort_value=3, act_id="act_001")]}
        table.get_item.return_value = {"Item": {"nova_session_id": "sess_abc"}}
        mock_boto3.resource.return_value.Table.return_value = table

        s3_client = MagicMock()
        s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "not found"}},
            "GetObject",
        )
        mock_boto3.client.return_value = s3_client

        result = handler(valid_event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 404
        assert "Trace file not found" in body["error"]

    @patch("get_step_trace.find_trace_s3_key", return_value="uc/ex/sess/act_001_nav_calls.json")
    @patch("get_step_trace.boto3")
    @patch("get_step_trace.require_scopes")
    def test_s3_get_object_other_error(self, mock_scopes, mock_boto3, mock_find, mock_env_vars, valid_event):
        mock_scopes.return_value = ({"identity": "user"}, None)
        table = MagicMock()
        table.query.return_value = {"Items": [_make_step_item(sort_value=3, act_id="act_001")]}
        table.get_item.return_value = {"Item": {"nova_session_id": "sess_abc"}}
        mock_boto3.resource.return_value.Table.return_value = table

        s3_client = MagicMock()
        s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "boom"}},
            "GetObject",
        )
        mock_boto3.client.return_value = s3_client

        result = handler(valid_event, None)
        assert result["statusCode"] == 500

    @patch("get_step_trace.parse_trace_json", side_effect=ValueError("bad"))
    @patch("get_step_trace.find_trace_s3_key", return_value="uc/ex/sess/act_001_nav_calls.json")
    @patch("get_step_trace.boto3")
    @patch("get_step_trace.require_scopes")
    def test_parse_failure(self, mock_scopes, mock_boto3, mock_find, mock_parse, mock_env_vars, valid_event):
        mock_scopes.return_value = ({"identity": "user"}, None)
        table = MagicMock()
        table.query.return_value = {"Items": [_make_step_item(sort_value=3, act_id="act_001")]}
        table.get_item.return_value = {"Item": {"nova_session_id": "sess_abc"}}
        mock_boto3.resource.return_value.Table.return_value = table

        s3_client = MagicMock()
        body_mock = MagicMock()
        body_mock.read.return_value = b"bad json"
        s3_client.get_object.return_value = {"Body": body_mock}
        mock_boto3.client.return_value = s3_client

        result = handler(valid_event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 404
        assert "Failed to parse trace data" in body["error"]

    @patch("get_step_trace.require_scopes", side_effect=RuntimeError("boom"))
    def test_unexpected_exception(self, mock_scopes, valid_event):
        result = handler(valid_event, None)
        assert result["statusCode"] == 500
