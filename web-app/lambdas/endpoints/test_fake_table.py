"""Tests for the ``FakeDynamoResource`` helper around ``FakeTable`` and ``FakeTable.query`` key conditions."""
import pytest
from boto3.dynamodb.conditions import Key

from fake_table import FakeDynamoResource, FakeTable


@pytest.fixture
def table():
    return FakeTable([
        {'pk': 'USECASE#a', 'sk': 'METADATA', 'name': 'A'},
        {'pk': 'USECASE#b', 'sk': 'METADATA', 'name': 'B'},
    ])


def test_resource_table_returns_the_fake_table(table):
    resource = FakeDynamoResource(table, 'tbl')
    assert resource.Table('tbl') is table


def test_resource_table_rejects_other_names(table):
    resource = FakeDynamoResource(table, 'tbl')
    with pytest.raises(NotImplementedError):
        resource.Table('other')


def test_batch_get_item_returns_existing_items_only(table):
    resource = FakeDynamoResource(table, 'tbl')
    response = resource.batch_get_item(RequestItems={'tbl': {'Keys': [
        {'pk': 'USECASE#a', 'sk': 'METADATA'},
        {'pk': 'USECASE#missing', 'sk': 'METADATA'},
        {'pk': 'USECASE#b', 'sk': 'METADATA'},
    ]}})
    items = response['Responses']['tbl']
    assert [i['name'] for i in items] == ['A', 'B']
    assert response['UnprocessedKeys'] == {}
    assert resource.batch_get_calls == [[
        {'pk': 'USECASE#a', 'sk': 'METADATA'},
        {'pk': 'USECASE#missing', 'sk': 'METADATA'},
        {'pk': 'USECASE#b', 'sk': 'METADATA'},
    ]]


def test_batch_get_item_rejects_more_than_100_keys(table):
    resource = FakeDynamoResource(table, 'tbl')
    keys = [{'pk': f'USECASE#{i}', 'sk': 'METADATA'} for i in range(101)]
    with pytest.raises(ValueError):
        resource.batch_get_item(RequestItems={'tbl': {'Keys': keys}})


def test_batch_get_item_rejects_unknown_table(table):
    resource = FakeDynamoResource(table, 'tbl')
    with pytest.raises(NotImplementedError):
        resource.batch_get_item(RequestItems={'other': {'Keys': [{'pk': 'x', 'sk': 'y'}]}})


# ---------------------------------------------------------------------------
# query key conditions
# ---------------------------------------------------------------------------


@pytest.fixture
def executions():
    pk = 'USECASE_EXECUTION#u1'
    return FakeTable([
        {'pk': pk, 'sk': 'EXECUTION#0192a000-0000-7000-8000-000000000001', 'n': 1},
        {'pk': pk, 'sk': 'EXECUTION#0192a000-0000-7000-8000-000000000002', 'n': 2},
        {'pk': pk, 'sk': 'EXECUTION#0192a000-0000-7000-8000-000000000003', 'n': 3},
        {'pk': pk, 'sk': 'OTHER#1', 'n': 9},
        {'pk': 'USECASE_EXECUTION#u2', 'sk': 'EXECUTION#0192a000-0000-7000-8000-000000000002', 'n': 22},
    ])


def test_query_by_pk_only(executions):
    items = executions.query(KeyConditionExpression=Key('pk').eq('USECASE_EXECUTION#u1'))['Items']
    assert sorted(i['n'] for i in items) == [1, 2, 3, 9]


def test_query_begins_with(executions):
    condition = Key('pk').eq('USECASE_EXECUTION#u1') & Key('sk').begins_with('EXECUTION#')
    assert sorted(i['n'] for i in executions.query(KeyConditionExpression=condition)['Items']) == [1, 2, 3]


def test_query_between_is_inclusive_on_both_ends(executions):
    condition = Key('pk').eq('USECASE_EXECUTION#u1') & Key('sk').between(
        'EXECUTION#0192a000-0000-7000-8000-000000000002', 'EXECUTION#0192a000-0000-7000-8000-000000000003')
    assert sorted(i['n'] for i in executions.query(KeyConditionExpression=condition)['Items']) == [2, 3]


def test_query_between_with_no_match_is_empty(executions):
    condition = Key('pk').eq('USECASE_EXECUTION#u1') & Key('sk').between('EXECUTION#1', 'EXECUTION#2')
    assert executions.query(KeyConditionExpression=condition)['Items'] == []


def test_query_rejects_unsupported_sk_operators(executions):
    with pytest.raises(NotImplementedError):
        executions.query(KeyConditionExpression=Key('pk').eq('USECASE_EXECUTION#u1') & Key('sk').gt('EXECUTION#'))
