"""variable_merge: the one loader for effective use-case variables.

Precedence (lowest → highest): application ``VARIABLES`` → use case
``USECASE_VARIABLES`` → CLI / suite overrides (``merge_variables``).
"""
from unittest.mock import MagicMock

import pytest
from boto3.dynamodb.types import TypeSerializer

from fake_table import FakeTable
from variable_merge import (
    client_item_reader,
    load_application_variables,
    load_effective_usecase_variables,
    merge_layers,
    merge_variables,
    rows_to_dict,
    table_item_reader,
    variables_from_item,
)

APP_ID = 'app-1'
UC_ID = 'uc-1'
APP_KEY = {'pk': f'APPLICATION#{APP_ID}', 'sk': 'VARIABLES'}
UC_KEY = {'pk': f'USECASE#{UC_ID}', 'sk': 'USECASE_VARIABLES'}


def _rows(*pairs):
    return [{'key': k, 'value': v} for k, v in pairs]


class TestMergeVariables:
    def test_cli_wins_over_usecase_wins_over_secrets(self):
        merged = merge_variables({'u': 's', 'p': 's'}, {'u': 'uc'}, {'u': 'cli'})
        assert merged == {'u': 'cli', 'p': 's'}

    def test_inputs_are_not_mutated(self):
        secrets, usecase, cli = {'a': '1'}, {'a': '2'}, {}
        merge_variables(secrets, usecase, cli)
        assert (secrets, usecase, cli) == ({'a': '1'}, {'a': '2'}, {})


class TestVariablesFromItem:
    def test_missing_item_is_empty(self):
        assert variables_from_item(None) == {}
        assert variables_from_item({}) == {}

    def test_rows_keep_stored_order(self):
        item = {'variables': _rows(('b', '2'), ('a', '1'))}
        assert list(variables_from_item(item).items()) == [('b', '2'), ('a', '1')]

    def test_legacy_capitalised_rows(self):
        item = {'variables': [{'Key': 'a', 'Value': '1'}]}
        assert variables_from_item(item) == {'a': '1'}

    def test_legacy_key_value_map(self):
        assert variables_from_item({'variables': {'a': '1', 'b': '2'}}) == {'a': '1', 'b': '2'}

    def test_entries_without_a_key_are_dropped(self):
        item = {'variables': [{'value': 'x'}, 'garbage', {'key': 'ok', 'value': '1'}]}
        assert variables_from_item(item) == {'ok': '1'}

    def test_empty_value_is_kept(self):
        assert variables_from_item({'variables': _rows(('a', ''))}) == {'a': ''}


class TestMergeLayers:
    def test_application_only_is_sorted_by_key(self):
        assert merge_layers({'b': '2', 'a': '1'}, {}) == [
            {'key': 'a', 'value': '1', 'source': 'application'},
            {'key': 'b', 'value': '2', 'source': 'application'},
        ]

    def test_usecase_only_keeps_stored_order(self):
        assert merge_layers({}, {'b': '2', 'a': '1'}) == [
            {'key': 'b', 'value': '2', 'source': 'usecase'},
            {'key': 'a', 'value': '1', 'source': 'usecase'},
        ]

    def test_disjoint_application_rows_come_first(self):
        assert merge_layers({'z': 'app'}, {'a': 'uc'}) == [
            {'key': 'z', 'value': 'app', 'source': 'application'},
            {'key': 'a', 'value': 'uc', 'source': 'usecase'},
        ]

    def test_usecase_shadows_application_key_once(self):
        rows = merge_layers({'base': 'app', 'other': 'app'}, {'base': 'uc'})
        assert rows == [
            {'key': 'other', 'value': 'app', 'source': 'application'},
            {'key': 'base', 'value': 'uc', 'source': 'usecase'},
        ]
        assert [r['key'] for r in rows].count('base') == 1

    def test_both_empty(self):
        assert merge_layers({}, {}) == []

    def test_inputs_are_not_mutated(self):
        app, uc = {'a': '1'}, {'a': '2'}
        merge_layers(app, uc)
        assert (app, uc) == ({'a': '1'}, {'a': '2'})


class TestRowsToDict:
    def test_drops_source_and_keeps_order(self):
        rows = merge_layers({'b': 'app'}, {'a': 'uc'})
        assert list(rows_to_dict(rows).items()) == [('b', 'app'), ('a', 'uc')]


class TestLoadEffectiveUsecaseVariables:
    def _reader(self, items):
        table = FakeTable(items)
        calls = []

        def read_item(pk, sk):
            calls.append((pk, sk))
            return table.get_item(Key={'pk': pk, 'sk': sk}).get('Item')

        return read_item, calls

    def test_two_get_items_when_application_known(self):
        read_item, calls = self._reader([
            {**APP_KEY, 'variables': _rows(('base', 'app'), ('zone', 'eu'))},
            {**UC_KEY, 'variables': _rows(('base', 'uc'))},
        ])
        rows = load_effective_usecase_variables(read_item, UC_ID, APP_ID)
        assert rows == [
            {'key': 'zone', 'value': 'eu', 'source': 'application'},
            {'key': 'base', 'value': 'uc', 'source': 'usecase'},
        ]
        assert sorted(calls) == sorted([(APP_KEY['pk'], 'VARIABLES'), (UC_KEY['pk'], 'USECASE_VARIABLES')])

    @pytest.mark.parametrize('application_id', [None, ''])
    def test_no_application_reads_only_the_usecase_layer(self, application_id):
        read_item, calls = self._reader([{**UC_KEY, 'variables': _rows(('b', '2'), ('a', '1'))}])
        rows = load_effective_usecase_variables(read_item, UC_ID, application_id)
        assert rows == [
            {'key': 'b', 'value': '2', 'source': 'usecase'},
            {'key': 'a', 'value': '1', 'source': 'usecase'},
        ]
        assert calls == [(UC_KEY['pk'], 'USECASE_VARIABLES')]

    def test_nothing_stored_is_empty(self):
        read_item, _ = self._reader([])
        assert load_effective_usecase_variables(read_item, UC_ID, APP_ID) == []

    def test_load_application_variables(self):
        read_item, calls = self._reader([{**APP_KEY, 'variables': _rows(('b', '2'), ('a', '1'))}])
        assert load_application_variables(read_item, APP_ID) == {'b': '2', 'a': '1'}
        assert calls == [(APP_KEY['pk'], 'VARIABLES')]
        assert load_application_variables(read_item, None) == {}
        assert len(calls) == 1


# (app layer, usecase layer, CLI layer) -> effective {key: value} as the
# execution snapshot sees it (merge_variables with the effective dict as
# ``usecase_vars``).
PRECEDENCE_TABLE = [
    ({'a': 'app'}, {}, {}, {'a': 'app'}),                                  # app only
    ({}, {'a': 'uc'}, {}, {'a': 'uc'}),                                    # usecase only
    ({'a': 'app'}, {'b': 'uc'}, {}, {'a': 'app', 'b': 'uc'}),              # disjoint
    ({'a': 'app'}, {'a': 'uc'}, {}, {'a': 'uc'}),                          # usecase wins
    ({'a': 'app'}, {'a': 'uc'}, {'a': 'cli'}, {'a': 'cli'}),               # CLI wins over both
    ({'a': 'app'}, {}, {'a': 'cli'}, {'a': 'cli'}),                        # CLI wins over app alone
    ({}, {}, {}, {}),
]


@pytest.mark.parametrize('app_vars,usecase_vars,cli_vars,expected', PRECEDENCE_TABLE)
def test_precedence_table(app_vars, usecase_vars, cli_vars, expected):
    effective = rows_to_dict(merge_layers(app_vars, usecase_vars))
    assert merge_variables({}, effective, cli_vars) == expected


class TestItemReaders:
    def test_table_item_reader_uses_resource_api(self):
        table = FakeTable([{**UC_KEY, 'variables': _rows(('a', '1'))}])
        read_item = table_item_reader(table)
        assert read_item(UC_KEY['pk'], UC_KEY['sk']) == {**UC_KEY, 'variables': _rows(('a', '1'))}
        assert read_item('USECASE#nope', 'USECASE_VARIABLES') is None

    def test_client_item_reader_deserialises_typed_items(self):
        client = MagicMock()
        serializer = TypeSerializer()
        client.get_item.return_value = {'Item': {
            'pk': serializer.serialize(UC_KEY['pk']),
            'sk': serializer.serialize(UC_KEY['sk']),
            'variables': serializer.serialize(_rows(('a', '1'))),
        }}
        read_item = client_item_reader(client, 'tbl')
        assert read_item(UC_KEY['pk'], UC_KEY['sk']) == {**UC_KEY, 'variables': _rows(('a', '1'))}
        client.get_item.assert_called_once_with(
            TableName='tbl', Key={'pk': {'S': UC_KEY['pk']}, 'sk': {'S': UC_KEY['sk']}})

    def test_client_item_reader_missing_item(self):
        client = MagicMock()
        client.get_item.return_value = {}
        assert client_item_reader(client, 'tbl')('p', 's') is None
