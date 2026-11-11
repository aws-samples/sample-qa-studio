"""Tests for Option C cache invalidation on failed executions.

Two layers:

1. ``cache_invalidation`` module — unit tests for the three public
   helpers with mocked boto3 clients.
2. ``update_execution_status`` integration — the PATCH endpoint must
   call ``cleanup_cache_artifacts`` when ``status == 'failed'`` and
   skip it for every other status.

The cache wipe itself lives in ``execution_transitions`` (shared with the
reconciler); its own tests are in ``test_execution_transitions.py``.

All tests use ``MagicMock`` + ``monkeypatch``; no real AWS calls.
"""
import json
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    """Common env vars the Lambdas expect."""
    monkeypatch.setenv("TABLE_NAME", "test-table")
    monkeypatch.setenv("S3_BUCKET", "test-bucket")


def _make_event(status, *, usecase_id="uc-1", execution_id="exec-1"):
    """Build an API-GW proxy event for the update_execution_status handler."""
    return {
        "httpMethod": "PATCH",
        "pathParameters": {"id": usecase_id, "executionId": execution_id},
        "requestContext": {
            "authorizer": {
                "client_id": "test-client",
                "scope": "api/executions.write",
            },
        },
        "body": json.dumps({"status": status}),
    }


def _existing_execution_item(usecase_id="uc-1", execution_id="exec-1"):
    """DDB get_item response for an already-created execution."""
    return {
        "Item": {
            "pk": {"S": f"USECASE_EXECUTION#{usecase_id}"},
            "sk": {"S": f"EXECUTION#{execution_id}"},
            "status": {"S": "running"},
        },
    }


# ---------------------------------------------------------------------------
# 1. cache_invalidation module — unit tests
# ---------------------------------------------------------------------------


class TestClearStepCacheFields:
    """Per-step ``REMOVE`` issued on every STEP record for the usecase."""

    def test_removes_cache_fields_from_each_step(self):
        from cache_invalidation import clear_step_cache_fields

        mock_table = MagicMock()
        mock_table.query.return_value = {
            "Items": [
                {"pk": "USECASE#uc-1", "sk": "STEP#s-1"},
                {"pk": "USECASE#uc-1", "sk": "STEP#s-2"},
            ],
        }

        clear_step_cache_fields(mock_table, "uc-1")

        # One update_item per step, using REMOVE on all four cache fields.
        assert mock_table.update_item.call_count == 2
        call = mock_table.update_item.call_args_list[0]
        assert call.kwargs["Key"] == {"pk": "USECASE#uc-1", "sk": "STEP#s-1"}
        expr = call.kwargs["UpdateExpression"]
        assert expr.startswith("REMOVE ")
        for field in (
            "cached_steps", "cache_last_updated",
            "trajectory_s3_key", "trajectory_last_updated",
        ):
            assert field in expr, f"REMOVE expression missing {field!r}"

    def test_pagination_walks_all_pages(self):
        from cache_invalidation import clear_step_cache_fields

        mock_table = MagicMock()
        # First page has a LastEvaluatedKey → helper must re-query.
        mock_table.query.side_effect = [
            {
                "Items": [{"pk": "USECASE#uc-1", "sk": "STEP#s-1"}],
                "LastEvaluatedKey": {"pk": "x", "sk": "y"},
            },
            {"Items": [{"pk": "USECASE#uc-1", "sk": "STEP#s-2"}]},
        ]

        clear_step_cache_fields(mock_table, "uc-1")

        assert mock_table.query.call_count == 2
        assert mock_table.update_item.call_count == 2

    def test_per_step_update_failure_does_not_abort(self):
        """One bad step shouldn't stop cleanup of the rest."""
        from cache_invalidation import clear_step_cache_fields

        mock_table = MagicMock()
        mock_table.query.return_value = {
            "Items": [
                {"pk": "USECASE#uc-1", "sk": "STEP#s-1"},
                {"pk": "USECASE#uc-1", "sk": "STEP#s-2"},
            ],
        }
        mock_table.update_item.side_effect = [
            Exception("throttle"),  # s-1 fails
            {},                     # s-2 succeeds
        ]

        # Must not raise.
        clear_step_cache_fields(mock_table, "uc-1")
        assert mock_table.update_item.call_count == 2

    def test_query_failure_is_swallowed(self):
        from cache_invalidation import clear_step_cache_fields

        mock_table = MagicMock()
        mock_table.query.side_effect = Exception("boom")

        # Must not raise.
        clear_step_cache_fields(mock_table, "uc-1")
        mock_table.update_item.assert_not_called()


class TestDeleteTrajectoryFiles:
    """S3 object deletion filtered to trajectory path pattern."""

    def test_only_deletes_trajectory_files(self):
        from cache_invalidation import delete_trajectory_files

        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "uc-1/step-1/trajectories/a.json"},   # yes
                {"Key": "uc-1/step-1/screenshots/a.png"},     # no — screenshot
                {"Key": "uc-1/step-2/trajectories/b.json"},   # yes
                {"Key": "uc-1/step-2/logs/c.log"},            # no — log
            ],
            "IsTruncated": False,
        }

        delete_trajectory_files(mock_s3, "bucket", "uc-1")

        mock_s3.delete_objects.assert_called_once()
        call = mock_s3.delete_objects.call_args
        keys = [o["Key"] for o in call.kwargs["Delete"]["Objects"]]
        assert keys == [
            "uc-1/step-1/trajectories/a.json",
            "uc-1/step-2/trajectories/b.json",
        ]

    def test_no_matching_objects_means_no_delete(self):
        from cache_invalidation import delete_trajectory_files

        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {
            "Contents": [{"Key": "uc-1/step-1/screenshots/a.png"}],
            "IsTruncated": False,
        }

        delete_trajectory_files(mock_s3, "bucket", "uc-1")
        mock_s3.delete_objects.assert_not_called()

    def test_handles_pagination(self):
        from cache_invalidation import delete_trajectory_files

        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.side_effect = [
            {
                "Contents": [{"Key": "uc-1/s/trajectories/1.json"}],
                "IsTruncated": True,
                "NextContinuationToken": "token-2",
            },
            {
                "Contents": [{"Key": "uc-1/s/trajectories/2.json"}],
                "IsTruncated": False,
            },
        ]

        delete_trajectory_files(mock_s3, "bucket", "uc-1")
        assert mock_s3.list_objects_v2.call_count == 2
        assert mock_s3.delete_objects.call_count == 2

    def test_list_failure_does_not_raise(self):
        from cache_invalidation import delete_trajectory_files

        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.side_effect = Exception("network")

        # Must not raise.
        delete_trajectory_files(mock_s3, "bucket", "uc-1")


class TestCleanupCacheArtifacts:
    """Orchestrator: DDB clear + optional S3 delete."""

    def test_calls_both_paths_when_bucket_set(self, monkeypatch):
        import cache_invalidation

        calls = []
        monkeypatch.setattr(
            cache_invalidation, "clear_step_cache_fields",
            lambda table, uc: calls.append(("ddb", uc)),
        )
        monkeypatch.setattr(
            cache_invalidation, "delete_trajectory_files",
            lambda s3, bucket, uc: calls.append(("s3", bucket, uc)),
        )
        monkeypatch.setattr(cache_invalidation.boto3, "client", MagicMock())

        cache_invalidation.cleanup_cache_artifacts(MagicMock(), "uc-1", "bucket")

        assert calls == [("ddb", "uc-1"), ("s3", "bucket", "uc-1")]

    def test_skips_s3_when_bucket_empty(self, monkeypatch):
        import cache_invalidation

        calls = []
        monkeypatch.setattr(
            cache_invalidation, "clear_step_cache_fields",
            lambda table, uc: calls.append("ddb"),
        )
        monkeypatch.setattr(
            cache_invalidation, "delete_trajectory_files",
            lambda *args, **kwargs: calls.append("s3"),
        )

        cache_invalidation.cleanup_cache_artifacts(MagicMock(), "uc-1", "")

        assert calls == ["ddb"]


# ---------------------------------------------------------------------------
# 2. update_execution_status integration
# ---------------------------------------------------------------------------


@pytest.fixture
def patched_status_lambda(monkeypatch):
    """Wire update_execution_status with mocked DDB client + cleanup spy."""
    # Fresh import per fixture so module-level singletons don't leak
    # between tests that modify the same attrs.
    import importlib
    import update_execution_status
    importlib.reload(update_execution_status)

    mock_ddb = MagicMock()
    mock_ddb.get_item.return_value = _existing_execution_item()
    monkeypatch.setattr(update_execution_status, "dynamodb", mock_ddb)

    # EventBridge is not the subject under test; silence it.
    mock_eb = MagicMock()
    monkeypatch.setattr(update_execution_status, "eventbridge", mock_eb)

    # The cache wipe moved into the shared terminal transition
    # (execution_transitions.finalize_terminal_transition); the handler
    # passes its clients through, so the spy must sit on that module.
    import execution_transitions
    cleanup_spy = MagicMock()
    monkeypatch.setattr(
        execution_transitions, "cleanup_cache_artifacts", cleanup_spy,
    )

    # The shared module calls ``boto3.resource('dynamodb').Table(...)`` only
    # to build the argument for the cleanup helper. Stub so that call
    # doesn't try to reach AWS.
    fake_resource = MagicMock()
    monkeypatch.setattr(
        execution_transitions.boto3, "resource",
        lambda *_a, **_kw: fake_resource,
    )

    return update_execution_status, cleanup_spy, mock_ddb


class TestUpdateExecutionStatusInvalidation:
    def test_failed_status_triggers_cleanup(self, patched_status_lambda):
        module, cleanup_spy, _ = patched_status_lambda

        response = module.handler(_make_event("failed"), None)

        assert response["statusCode"] == 200
        cleanup_spy.assert_called_once()
        # Args: (table, usecase_id, s3_bucket)
        _table_arg, uc_arg, bucket_arg = cleanup_spy.call_args.args
        assert uc_arg == "uc-1"
        assert bucket_arg == "test-bucket"

    @pytest.mark.parametrize(
        "non_failure_status", ["success", "completed", "running", "pending"],
    )
    def test_non_failed_statuses_do_not_trigger_cleanup(
        self, patched_status_lambda, non_failure_status,
    ):
        module, cleanup_spy, _ = patched_status_lambda

        response = module.handler(_make_event(non_failure_status), None)

        assert response["statusCode"] == 200
        cleanup_spy.assert_not_called()

    def test_cleanup_exception_does_not_fail_the_request(
        self, patched_status_lambda,
    ):
        module, cleanup_spy, _ = patched_status_lambda
        cleanup_spy.side_effect = Exception("ddb down")

        response = module.handler(_make_event("failed"), None)

        # Primary action (status update) succeeded; cleanup failure
        # must not degrade the caller's response.
        assert response["statusCode"] == 200
        cleanup_spy.assert_called_once()


import pytest as _pytest  # noqa: E402
from authz_test_support import resource_access_granted as _resource_access_granted  # noqa: E402


@_pytest.fixture(autouse=True)
def _access_granted():
    """Handler-logic tests: ownership is covered by test_execution_routes_access.py."""
    with _resource_access_granted():
        yield
