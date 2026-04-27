"""Bug condition exploration tests for stale usecase names in suite listing.

**Validates: Requirements 1.1, 1.2, 1.3**

These tests demonstrate the bug: `list_suite_usecases` returns stale `usecase_name`
from mapping records instead of the current name from canonical usecase records.

Bug Condition: When a usecase has been renamed after being added to a suite,
the mapping record's `usecase_name` diverges from the canonical record's `name`.
The handler reads directly from the mapping record and never consults the
canonical record.

CRITICAL: These tests MUST FAIL on unfixed code — failure confirms the bug exists.
DO NOT fix the test or the code when it fails.
"""

import json
import pytest
from unittest.mock import Mock, patch, call
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from list_suite_usecases import handler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_event(suite_id: str) -> dict:
    """Build a minimal API Gateway event for list_suite_usecases."""
    return {
        'pathParameters': {'suite_id': suite_id},
        'requestContext': {
            'authorizer': {
                'email': 'test@example.com',
                'sub': 'user-123',
                'scope': 'api/suite.read api/admin',
            }
        },
    }


def _make_suite(suite_id: str) -> dict:
    """Create a mock test suite record."""
    return {
        'pk': 'TEST_SUITES',
        'sk': f'SUITE#{suite_id}',
        'id': suite_id,
        'name': 'Test Suite',
        'scope': 'suite:test',
        'total_usecases': 0,
    }


def _make_mapping(suite_id: str, usecase_id: str, stale_name: str) -> dict:
    """Create a suite-usecase mapping record with a stale name."""
    return {
        'pk': f'SUITE#{suite_id}',
        'sk': f'USECASE#{usecase_id}',
        'suite_id': suite_id,
        'usecase_id': usecase_id,
        'usecase_name': stale_name,
        'usecase_scope': 'usecase:default',
        'added_by': 'user@example.com',
        'added_at': '2024-01-01T10:00:00Z',
    }


def _make_canonical(usecase_id: str, current_name: str) -> dict:
    """Create a canonical usecase record with the current (updated) name."""
    return {
        'pk': 'USECASES',
        'sk': f'USECASE#{usecase_id}',
        'id': usecase_id,
        'name': current_name,
        'description': 'A test case',
        'scope': 'usecase:default',
    }


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

class TestStaleUsecaseNameBugCondition:
    """Bug condition: handler returns stale usecase_name from mapping record
    instead of the current name from the canonical usecase record.

    On UNFIXED code these tests FAIL — confirming the bug exists.

    **Validates: Requirements 1.1, 1.2, 1.3**
    """

    @patch('list_suite_usecases.boto3')
    def test_single_usecase_renamed_once(self, mock_boto3):
        """Single usecase renamed: mapping has "Login Test", canonical has
        "Authentication Flow". Handler should return "Authentication Flow".

        On UNFIXED code: handler returns "Login Test" (stale) — test FAILS.

        **Validates: Requirements 1.1, 1.2**
        """
        suite_id = 'suite-stale-001'
        usecase_id = 'uc-stale-001'
        stale_name = 'Login Test'
        current_name = 'Authentication Flow'

        mock_dynamodb = mock_boto3.resource.return_value
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table

        # Suite exists
        mock_table.get_item.return_value = {'Item': _make_suite(suite_id)}

        # Mapping record has the OLD name
        mock_table.query.return_value = {
            'Items': [_make_mapping(suite_id, usecase_id, stale_name)]
        }

        # Canonical record has the NEW name
        mock_dynamodb.batch_get_item.return_value = {
            'Responses': {
                'accept-ai': [_make_canonical(usecase_id, current_name)]
            }
        }

        event = _build_event(suite_id)
        response = handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body['usecases']) == 1

        returned_name = body['usecases'][0]['usecase_name']
        assert returned_name == current_name, (
            f"Expected current canonical name '{current_name}', "
            f"but handler returned stale mapping name '{returned_name}'. "
            f"This confirms the bug: handler reads usecase_name from the "
            f"mapping record instead of the canonical record."
        )

    @patch('list_suite_usecases.boto3')
    def test_multiple_usecases_renamed_in_same_suite(self, mock_boto3):
        """Three usecases renamed in the same suite. Handler should return
        all current names from canonical records.

        On UNFIXED code: handler returns all stale names — test FAILS.

        **Validates: Requirements 1.1, 1.2**
        """
        suite_id = 'suite-stale-002'
        renames = [
            ('uc-multi-001', 'Login Test',    'Authentication Flow'),
            ('uc-multi-002', 'Checkout Test',  'Purchase Flow'),
            ('uc-multi-003', 'Search Test',    'Discovery Engine Test'),
        ]

        mock_dynamodb = mock_boto3.resource.return_value
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table

        mock_table.get_item.return_value = {'Item': _make_suite(suite_id)}

        mappings = [
            _make_mapping(suite_id, uid, stale)
            for uid, stale, _ in renames
        ]
        mock_table.query.return_value = {'Items': mappings}

        # Canonical records have the NEW names
        canonical_records = [
            _make_canonical(uid, current)
            for uid, _, current in renames
        ]
        mock_dynamodb.batch_get_item.return_value = {
            'Responses': {'accept-ai': canonical_records}
        }

        event = _build_event(suite_id)
        response = handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body['usecases']) == 3

        for usecase_obj, (uid, stale, current) in zip(body['usecases'], renames):
            returned_name = usecase_obj['usecase_name']
            assert returned_name == current, (
                f"Usecase {uid}: expected '{current}', got '{returned_name}'. "
                f"Stale mapping name '{stale}' was returned instead."
            )

    @patch('list_suite_usecases.boto3')
    def test_same_usecase_stale_in_multiple_suites(self, mock_boto3):
        """Same usecase belongs to two suites, both with stale names.
        Handler should return the current name for each suite.

        On UNFIXED code: both suites return the stale name — test FAILS.

        **Validates: Requirements 1.1, 1.2, 1.3**
        """
        usecase_id = 'uc-shared-001'
        stale_name = 'Checkout Test'
        current_name = 'Purchase Flow'

        suite_ids = ['suite-a-001', 'suite-b-001']

        mock_dynamodb = mock_boto3.resource.return_value
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table

        for sid in suite_ids:
            # Reset mocks for each suite call
            mock_table.get_item.return_value = {'Item': _make_suite(sid)}
            mock_table.query.return_value = {
                'Items': [_make_mapping(sid, usecase_id, stale_name)]
            }

            # Canonical record has the NEW name
            mock_dynamodb.batch_get_item.return_value = {
                'Responses': {
                    'accept-ai': [_make_canonical(usecase_id, current_name)]
                }
            }

            event = _build_event(sid)
            response = handler(event, None)

            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert len(body['usecases']) == 1

            returned_name = body['usecases'][0]['usecase_name']
            assert returned_name == current_name, (
                f"Suite {sid}: expected '{current_name}', got '{returned_name}'. "
                f"Stale mapping name '{stale_name}' was returned. "
                f"Bug affects all suites containing the renamed usecase."
            )

    # ------------------------------------------------------------------
    # Property-based exploration
    # ------------------------------------------------------------------

    @given(
        stale_name=st.text(
            alphabet=st.characters(whitelist_categories=('L', 'N', 'Z')),
            min_size=1,
            max_size=50,
        ).filter(lambda s: s.strip()),
        current_name=st.text(
            alphabet=st.characters(whitelist_categories=('L', 'N', 'Z')),
            min_size=1,
            max_size=50,
        ).filter(lambda s: s.strip()),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @patch('list_suite_usecases.boto3')
    def test_property_handler_returns_canonical_name_not_stale(
        self, mock_boto3, stale_name, current_name
    ):
        """Property 1: Bug Condition — for ANY pair of (stale_name, current_name)
        where stale_name != current_name, the handler should return current_name.

        On UNFIXED code: handler always returns stale_name — test FAILS.

        **Validates: Requirements 1.1, 1.2**
        """
        from hypothesis import assume
        assume(stale_name.strip() != current_name.strip())

        suite_id = 'suite-prop-001'
        usecase_id = 'uc-prop-001'

        mock_dynamodb = mock_boto3.resource.return_value
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table

        mock_table.get_item.return_value = {'Item': _make_suite(suite_id)}
        mock_table.query.return_value = {
            'Items': [_make_mapping(suite_id, usecase_id, stale_name)]
        }

        # Canonical record has the current (updated) name
        mock_dynamodb.batch_get_item.return_value = {
            'Responses': {
                'accept-ai': [_make_canonical(usecase_id, current_name)]
            }
        }

        event = _build_event(suite_id)
        response = handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body['usecases']) == 1

        returned_name = body['usecases'][0]['usecase_name']
        assert returned_name == current_name, (
            f"Expected canonical name '{current_name}', "
            f"got stale mapping name '{returned_name}'."
        )


# ---------------------------------------------------------------------------
# Preservation Property Tests
# ---------------------------------------------------------------------------

# Strategies for generating valid test data
_safe_id_strategy = st.from_regex(r'[a-zA-Z][a-zA-Z0-9\-_]{3,30}', fullmatch=True)

_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'Z')),
    min_size=1,
    max_size=60,
).filter(lambda s: s.strip())

_email_strategy = st.from_regex(
    r'[a-z]{3,8}@example\.com', fullmatch=True
)

_iso_timestamp_strategy = st.from_regex(
    r'2024-0[1-9]-[012][0-9]T[01][0-9]:[0-5][0-9]:[0-5][0-9]Z',
    fullmatch=True,
)


def _build_event_with_scope(suite_id: str, scope: str) -> dict:
    """Build an API Gateway event with a specific scope string."""
    return {
        'pathParameters': {'suite_id': suite_id},
        'requestContext': {
            'authorizer': {
                'email': 'test@example.com',
                'sub': 'user-123',
                'scope': scope,
            }
        },
    }


def _make_mapping_with_meta(
    suite_id: str,
    usecase_id: str,
    usecase_name: str,
    added_by: str,
    added_at: str,
) -> dict:
    """Create a suite-usecase mapping record with explicit metadata."""
    return {
        'pk': f'SUITE#{suite_id}',
        'sk': f'USECASE#{usecase_id}',
        'suite_id': suite_id,
        'usecase_id': usecase_id,
        'usecase_name': usecase_name,
        'usecase_scope': 'usecase:default',
        'added_by': added_by,
        'added_at': added_at,
    }


class TestPreservationProperties:
    """Preservation property tests: verify CURRENT correct behavior for
    non-buggy inputs (usecases that have NOT been renamed).

    These tests MUST PASS on the unfixed code. They will be re-run after
    the fix to verify no regressions.

    **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
    """

    # ------------------------------------------------------------------
    # Property 2a: Response shape — { usecases: [...], total: N }
    # ------------------------------------------------------------------

    @given(
        suite_id=_safe_id_strategy,
        num_usecases=st.integers(min_value=0, max_value=5),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @patch('list_suite_usecases.boto3')
    def test_property_response_shape(self, mock_boto3, suite_id, num_usecases):
        """Property 2a: Response shape — for all valid suite IDs with
        non-renamed usecases, response shape is { usecases: [...], total: N }
        where total equals len(usecases).

        **Validates: Requirements 3.4**
        """
        mock_dynamodb = mock_boto3.resource.return_value
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table

        mock_table.get_item.return_value = {'Item': _make_suite(suite_id)}

        mappings = [
            _make_mapping(suite_id, f'uc-{i}', f'Usecase {i}')
            for i in range(num_usecases)
        ]
        mock_table.query.return_value = {'Items': mappings}

        # Canonical records match mapping names (non-renamed)
        canonical_records = [
            _make_canonical(f'uc-{i}', f'Usecase {i}')
            for i in range(num_usecases)
        ]
        mock_dynamodb.batch_get_item.return_value = {
            'Responses': {'accept-ai': canonical_records}
        }

        event = _build_event(suite_id)
        response = handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])

        # Response must have exactly these two top-level keys
        assert 'usecases' in body, "Response must contain 'usecases' key"
        assert 'total' in body, "Response must contain 'total' key"
        assert isinstance(body['usecases'], list), "'usecases' must be a list"
        assert isinstance(body['total'], int), "'total' must be an integer"

        # total must equal len(usecases)
        assert body['total'] == len(body['usecases']), (
            f"total ({body['total']}) must equal len(usecases) ({len(body['usecases'])})"
        )
        assert body['total'] == num_usecases

    # ------------------------------------------------------------------
    # Property 2b: Metadata preservation — added_by and added_at from mapping
    # ------------------------------------------------------------------

    @given(
        suite_id=_safe_id_strategy,
        usecase_id=_safe_id_strategy,
        usecase_name=_name_strategy,
        added_by=_email_strategy,
        added_at=_iso_timestamp_strategy,
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @patch('list_suite_usecases.boto3')
    def test_property_metadata_preservation(
        self, mock_boto3, suite_id, usecase_id, usecase_name, added_by, added_at
    ):
        """Property 2b: Metadata preservation — for all mapping records,
        `added_by` and `added_at` always come from the mapping record.

        **Validates: Requirements 3.4**
        """
        mock_dynamodb = mock_boto3.resource.return_value
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table

        mock_table.get_item.return_value = {'Item': _make_suite(suite_id)}

        mapping = _make_mapping_with_meta(
            suite_id, usecase_id, usecase_name, added_by, added_at
        )
        mock_table.query.return_value = {'Items': [mapping]}

        # Canonical record matches mapping name (non-renamed)
        mock_dynamodb.batch_get_item.return_value = {
            'Responses': {
                'accept-ai': [_make_canonical(usecase_id, usecase_name)]
            }
        }

        event = _build_event(suite_id)
        response = handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body['usecases']) == 1

        uc = body['usecases'][0]
        assert uc['added_by'] == added_by, (
            f"added_by must come from mapping record: expected '{added_by}', "
            f"got '{uc['added_by']}'"
        )
        assert uc['added_at'] == added_at, (
            f"added_at must come from mapping record: expected '{added_at}', "
            f"got '{uc['added_at']}'"
        )

    # ------------------------------------------------------------------
    # Property 2c: 404 for missing suite
    # ------------------------------------------------------------------

    @given(suite_id=_safe_id_strategy)
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @patch('list_suite_usecases.boto3')
    def test_property_404_for_missing_suite(self, mock_boto3, suite_id):
        """Property 2c: 404 for missing suite — for all non-existent suite IDs,
        handler returns 404.

        **Validates: Requirements 3.4**
        """
        mock_table = Mock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        # Suite does NOT exist
        mock_table.get_item.return_value = {}

        event = _build_event(suite_id)
        response = handler(event, None)

        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert 'error' in body

    # ------------------------------------------------------------------
    # Property 2d: Scope validation
    # ------------------------------------------------------------------

    @given(suite_id=_safe_id_strategy)
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @patch('list_suite_usecases.boto3')
    def test_property_scope_validation(self, mock_boto3, suite_id):
        """Property 2d: Scope validation — for requests missing
        `api/suite.read` scope, handler returns appropriate error (403).

        **Validates: Requirements 3.5**
        """
        # Event with a scope that does NOT include api/suite.read or api/admin
        event = _build_event_with_scope(suite_id, 'api/usecases.read')
        response = handler(event, None)

        assert response['statusCode'] == 403
        body = json.loads(response['body'])
        assert 'error' in body or 'message' in body

    # ------------------------------------------------------------------
    # Property 2e: Non-renamed name correctness
    # ------------------------------------------------------------------

    @given(
        suite_id=_safe_id_strategy,
        usecase_id=_safe_id_strategy,
        usecase_name=_name_strategy,
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @patch('list_suite_usecases.boto3')
    def test_property_non_renamed_name_correctness(
        self, mock_boto3, suite_id, usecase_id, usecase_name
    ):
        """Property 2e: Non-renamed name correctness — for all usecases where
        mapping `usecase_name` equals canonical `name`, returned name matches both.

        This is the non-buggy case: no rename has occurred, so the mapping
        record's usecase_name is still correct.

        **Validates: Requirements 3.4**
        """
        mock_dynamodb = mock_boto3.resource.return_value
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table

        mock_table.get_item.return_value = {'Item': _make_suite(suite_id)}

        # Mapping name == canonical name (no rename occurred)
        mapping = _make_mapping(suite_id, usecase_id, usecase_name)
        mock_table.query.return_value = {'Items': [mapping]}

        # Canonical record matches mapping name
        mock_dynamodb.batch_get_item.return_value = {
            'Responses': {
                'accept-ai': [_make_canonical(usecase_id, usecase_name)]
            }
        }

        event = _build_event(suite_id)
        response = handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body['usecases']) == 1

        returned_name = body['usecases'][0]['usecase_name']
        assert returned_name == usecase_name, (
            f"For non-renamed usecase, returned name must match mapping name: "
            f"expected '{usecase_name}', got '{returned_name}'"
        )


# ---------------------------------------------------------------------------
# Edge Case Unit Tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case unit tests for the read-time name resolution logic.

    Covers BatchGetItem chunking, UnprocessedKeys retry, fallback to mapping
    name when canonical record is missing, empty suite short-circuit, and
    mixed canonical/missing scenarios.

    **Validates: Requirements 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4, 3.5**
    """

    # ------------------------------------------------------------------
    # 1. BatchGetItem with more than 25 usecases (chunking)
    # ------------------------------------------------------------------

    @patch('list_suite_usecases.boto3')
    def test_batch_get_item_chunks_into_batches_of_25(self, mock_boto3):
        """Create 30 mapping records. Verify the handler calls batch_get_item
        twice (25 + 5) and resolves all 30 names from canonical records.

        **Validates: Requirements 2.1, 2.2**
        """
        suite_id = 'suite-chunk-001'
        num_usecases = 30

        mock_dynamodb = mock_boto3.resource.return_value
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table

        mock_table.get_item.return_value = {'Item': _make_suite(suite_id)}

        mappings = [
            _make_mapping(suite_id, f'uc-{i}', f'Old Name {i}')
            for i in range(num_usecases)
        ]
        mock_table.query.return_value = {'Items': mappings}

        # Each batch_get_item call returns canonical records for that batch
        def batch_get_side_effect(RequestItems):
            table_name = list(RequestItems.keys())[0]
            keys = RequestItems[table_name]['Keys']
            records = []
            for key in keys:
                uid = key['sk'].replace('USECASE#', '')
                idx = int(uid.replace('uc-', ''))
                records.append(_make_canonical(uid, f'Current Name {idx}'))
            return {'Responses': {table_name: records}}

        mock_dynamodb.batch_get_item.side_effect = batch_get_side_effect

        event = _build_event(suite_id)
        response = handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['total'] == 30
        assert len(body['usecases']) == 30

        # Verify batch_get_item was called exactly twice (25 + 5)
        assert mock_dynamodb.batch_get_item.call_count == 2

        # Verify all names are resolved from canonical records
        for i, uc in enumerate(body['usecases']):
            assert uc['usecase_name'] == f'Current Name {i}', (
                f"Usecase uc-{i}: expected 'Current Name {i}', "
                f"got '{uc['usecase_name']}'"
            )

    # ------------------------------------------------------------------
    # 2. BatchGetItem with UnprocessedKeys retry
    # ------------------------------------------------------------------

    @patch('list_suite_usecases.boto3')
    def test_batch_get_item_retries_unprocessed_keys(self, mock_boto3):
        """Mock batch_get_item to return UnprocessedKeys on the first call,
        then return the remaining items on the second call. Verify all names
        are resolved.

        **Validates: Requirements 2.1, 2.2**
        """
        suite_id = 'suite-retry-001'
        table_name = 'accept-ai'

        mock_dynamodb = mock_boto3.resource.return_value
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table

        mock_table.get_item.return_value = {'Item': _make_suite(suite_id)}

        mappings = [
            _make_mapping(suite_id, f'uc-{i}', f'Stale Name {i}')
            for i in range(3)
        ]
        mock_table.query.return_value = {'Items': mappings}

        # First call: return 2 of 3 items, with 1 unprocessed
        first_response = {
            'Responses': {
                table_name: [
                    _make_canonical('uc-0', 'Fresh Name 0'),
                    _make_canonical('uc-1', 'Fresh Name 1'),
                ]
            },
            'UnprocessedKeys': {
                table_name: {
                    'Keys': [{'pk': 'USECASES', 'sk': 'USECASE#uc-2'}]
                }
            },
        }

        # Second call (retry): return the remaining item
        second_response = {
            'Responses': {
                table_name: [
                    _make_canonical('uc-2', 'Fresh Name 2'),
                ]
            },
        }

        mock_dynamodb.batch_get_item.side_effect = [first_response, second_response]

        event = _build_event(suite_id)
        response = handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['total'] == 3

        # All three names should be resolved from canonical records
        for i in range(3):
            assert body['usecases'][i]['usecase_name'] == f'Fresh Name {i}', (
                f"uc-{i}: expected 'Fresh Name {i}', "
                f"got '{body['usecases'][i]['usecase_name']}'"
            )

        # batch_get_item called twice: initial + retry for unprocessed
        assert mock_dynamodb.batch_get_item.call_count == 2

    # ------------------------------------------------------------------
    # 3. Fallback to mapping record name when canonical record is missing
    # ------------------------------------------------------------------

    @patch('list_suite_usecases.boto3')
    def test_fallback_to_mapping_name_when_canonical_missing(self, mock_boto3):
        """Create a mapping record but don't include the corresponding
        canonical record in the batch_get_item response (simulating a
        deleted usecase). Verify the handler falls back to the mapping
        record's usecase_name.

        **Validates: Requirements 3.4**
        """
        suite_id = 'suite-fallback-001'
        usecase_id = 'uc-deleted-001'
        mapping_name = 'Deleted Usecase Name'

        mock_dynamodb = mock_boto3.resource.return_value
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table

        mock_table.get_item.return_value = {'Item': _make_suite(suite_id)}

        mappings = [_make_mapping(suite_id, usecase_id, mapping_name)]
        mock_table.query.return_value = {'Items': mappings}

        # batch_get_item returns empty — canonical record doesn't exist
        mock_dynamodb.batch_get_item.return_value = {
            'Responses': {'accept-ai': []}
        }

        event = _build_event(suite_id)
        response = handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['total'] == 1
        assert body['usecases'][0]['usecase_name'] == mapping_name, (
            f"Expected fallback to mapping name '{mapping_name}', "
            f"got '{body['usecases'][0]['usecase_name']}'"
        )

    # ------------------------------------------------------------------
    # 4. Empty suite returns { usecases: [], total: 0 } without BatchGetItem
    # ------------------------------------------------------------------

    @patch('list_suite_usecases.boto3')
    def test_empty_suite_skips_batch_get_item(self, mock_boto3):
        """Verify that when a suite has no mapping records, batch_get_item
        is never called and the response is { usecases: [], total: 0 }.

        **Validates: Requirements 3.4**
        """
        suite_id = 'suite-empty-001'

        mock_dynamodb = mock_boto3.resource.return_value
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table

        mock_table.get_item.return_value = {'Item': _make_suite(suite_id)}
        mock_table.query.return_value = {'Items': []}

        event = _build_event(suite_id)
        response = handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body == {'usecases': [], 'total': 0}

        # batch_get_item must NOT be called for an empty suite
        mock_dynamodb.batch_get_item.assert_not_called()

    # ------------------------------------------------------------------
    # 5. Mixed: some canonical records exist, some don't
    # ------------------------------------------------------------------

    @patch('list_suite_usecases.boto3')
    def test_mixed_canonical_and_missing_records(self, mock_boto3):
        """Create 3 mapping records, but only return 2 canonical records
        from batch_get_item. Verify the 2 resolved names come from
        canonical and the 1 missing falls back to mapping name.

        **Validates: Requirements 2.1, 2.2, 3.4**
        """
        suite_id = 'suite-mixed-001'

        mock_dynamodb = mock_boto3.resource.return_value
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table

        mock_table.get_item.return_value = {'Item': _make_suite(suite_id)}

        mappings = [
            _make_mapping(suite_id, 'uc-exists-1', 'Old Name A'),
            _make_mapping(suite_id, 'uc-exists-2', 'Old Name B'),
            _make_mapping(suite_id, 'uc-deleted-1', 'Orphan Mapping Name'),
        ]
        mock_table.query.return_value = {'Items': mappings}

        # Only 2 of 3 canonical records exist
        mock_dynamodb.batch_get_item.return_value = {
            'Responses': {
                'accept-ai': [
                    _make_canonical('uc-exists-1', 'Current Name A'),
                    _make_canonical('uc-exists-2', 'Current Name B'),
                    # uc-deleted-1 intentionally absent
                ]
            }
        }

        event = _build_event(suite_id)
        response = handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['total'] == 3
        assert len(body['usecases']) == 3

        # First two: resolved from canonical records
        assert body['usecases'][0]['usecase_name'] == 'Current Name A'
        assert body['usecases'][1]['usecase_name'] == 'Current Name B'

        # Third: falls back to mapping record name
        assert body['usecases'][2]['usecase_name'] == 'Orphan Mapping Name', (
            f"Expected fallback to mapping name 'Orphan Mapping Name', "
            f"got '{body['usecases'][2]['usecase_name']}'"
        )
