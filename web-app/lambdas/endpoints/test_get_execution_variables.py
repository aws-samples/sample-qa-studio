"""
GET /usecase/{id}/executions/{executionId}/variables returns the execution's
variable snapshot as `execution_variables: {key: value}` for both stored shapes
of `EXECUTION#{id} / EXECUTION_VARIABLES.variables`: the list written by
`execute_usecase` and the map written by `execute_test_suite`. `variables`
(the use case's current USECASE_VARIABLES) and `runtime_variables` are
returned unchanged.
"""
import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from authz_test_support import EXEC_ID, UC_ID, make_event, owned_resources
from fake_table import FakeTable
from get_execution_variables import handler

EXECUTION_PK = f'EXECUTION#{EXEC_ID}'
USECASE_PK = f'USECASE#{UC_ID}'
RUNTIME = [{'key': 'order_id', 'value': '42'}]


def _execution_record(**attributes):
    return {'pk': EXECUTION_PK, 'sk': 'EXECUTION_VARIABLES', **attributes}


def _usecase_record(variables):
    return {'pk': USECASE_PK, 'sk': 'USECASE_VARIABLES', 'variables': variables}


@pytest.fixture(autouse=True)
def table_name(monkeypatch):
    monkeypatch.setenv('TABLE_NAME', 't')


def _call(*items, caller='viewer_a', scopes=None, table=None):
    table = table if table is not None else FakeTable(items)
    resource = MagicMock()
    resource.Table.return_value = table
    kwargs = {'scopes': scopes} if scopes is not None else {}
    event = make_event(caller, path={'id': UC_ID, 'executionId': EXEC_ID}, **kwargs)
    with owned_resources(), patch('get_execution_variables.boto3.resource', return_value=resource):
        return handler(event, None)


def _body(response, status=200):
    assert response['statusCode'] == status, response
    return json.loads(response['body'])


class TestExecutionVariablesSnapshot:
    def test_list_shape_is_returned_as_map(self):
        body = _body(_call(_execution_record(
            variables=[{'key': 'product', 'value': 'Laptop'}, {'key': 'env', 'value': 'staging'}],
            runtime_variables=RUNTIME,
        )))
        assert body['execution_variables'] == {'product': 'Laptop', 'env': 'staging'}

    def test_list_shape_keeps_stored_order(self):
        body = _body(_call(_execution_record(
            variables=[{'key': 'z', 'value': '1'}, {'key': 'a', 'value': '2'}],
        )))
        assert list(body['execution_variables']) == ['z', 'a']

    def test_legacy_capitalised_keys(self):
        body = _body(_call(_execution_record(
            variables=[{'Key': 'product', 'Value': 'Laptop'}, {'key': 'env', 'value': 'prod'}],
        )))
        assert body['execution_variables'] == {'product': 'Laptop', 'env': 'prod'}

    def test_list_rows_without_key_are_dropped(self):
        body = _body(_call(_execution_record(
            variables=[{'key': '', 'value': 'x'}, {'value': 'y'}, 'garbage', {'key': 'ok', 'value': 'v'}],
        )))
        assert body['execution_variables'] == {'ok': 'v'}

    def test_map_shape(self):
        body = _body(_call(_execution_record(
            variables={'product': 'Laptop', 'env': 'staging'},
            runtime_variables=RUNTIME,
        )))
        assert body['execution_variables'] == {'product': 'Laptop', 'env': 'staging'}

    def test_map_shape_values_are_strings(self):
        body = _body(_call(_execution_record(variables={'count': Decimal('3'), 'empty': None})))
        assert body['execution_variables'] == {'count': '3', 'empty': ''}

    def test_missing_record(self):
        body = _body(_call())
        assert body == {'variables': [], 'runtime_variables': [], 'execution_variables': {}}

    def test_missing_attribute(self):
        body = _body(_call(_execution_record(runtime_variables=RUNTIME)))
        assert body['execution_variables'] == {}
        assert body['runtime_variables'] == RUNTIME

    def test_empty_list(self):
        body = _body(_call(_execution_record(variables=[])))
        assert body['execution_variables'] == {}

    def test_table_error_returns_empty_snapshot(self):
        table = MagicMock()
        table.get_item.side_effect = RuntimeError('boom')
        body = _body(_call(table=table))
        assert body == {'variables': [], 'runtime_variables': [], 'execution_variables': {}}


class TestUnchangedFields:
    def test_runtime_variables_are_passed_through(self):
        body = _body(_call(_execution_record(variables=[{'key': 'a', 'value': '1'}], runtime_variables=RUNTIME)))
        assert body['runtime_variables'] == RUNTIME

    def test_variables_are_the_usecase_rows_lower_cased(self):
        body = _body(_call(
            _usecase_record([{'Key': 'product', 'Value': 'Old'}, {'key': 'env', 'value': 'dev'}]),
            _execution_record(variables=[{'key': 'product', 'value': 'Laptop'}]),
        ))
        assert body['variables'] == [{'key': 'product', 'value': 'Old'}, {'key': 'env', 'value': 'dev'}]
        assert body['execution_variables'] == {'product': 'Laptop'}

    def test_variables_keep_non_dict_rows_and_duplicates(self):
        body = _body(_call(_usecase_record(['raw', {'key': 'a', 'value': '1'}, {'key': 'a', 'value': '2'}])))
        assert body['variables'] == ['raw', {'key': 'a', 'value': '1'}, {'key': 'a', 'value': '2'}]

    def test_response_keys(self):
        assert set(_body(_call())) == {'variables', 'runtime_variables', 'execution_variables'}


class TestAccess:
    def test_requires_executions_read_scope(self):
        response = _call(_execution_record(variables=[]), scopes='api/usecases.read')
        assert response['statusCode'] == 403, response

    def test_other_team_is_denied(self):
        response = _call(_execution_record(variables=[]), caller='viewer_b')
        assert response['statusCode'] in (403, 404), response

    def test_invalid_execution_id(self):
        event = make_event('viewer_a', path={'id': UC_ID, 'executionId': '../x'})
        with owned_resources():
            response = handler(event, None)
        assert response['statusCode'] == 400, response
