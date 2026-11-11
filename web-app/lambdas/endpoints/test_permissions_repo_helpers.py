"""permissions_repo query/serialisation helpers and perm_audit.actor_from_identity."""
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('TABLE_NAME', 'test-table')

import permissions_repo  # noqa: E402
from perm_audit import actor_from_identity  # noqa: E402


@pytest.fixture
def table():
    t = MagicMock()
    with patch.object(permissions_repo, '_get_table', return_value=t):
        yield t


def _pages(*pages):
    """query side_effect returning each page; all but the last carry a LastEvaluatedKey."""
    responses = []
    for i, items in enumerate(pages):
        response = {'Items': items}
        if i < len(pages) - 1:
            response['LastEvaluatedKey'] = {'pk': 'p', 'sk': f'k{i}'}
        responses.append(response)
    return responses


class TestQueryAll:
    def test_follows_last_evaluated_key(self, table):
        table.query.side_effect = _pages([{'id': 1}], [{'id': 2}], [{'id': 3}])
        assert permissions_repo.list_teams() == [{'id': 1}, {'id': 2}, {'id': 3}]
        starts = [c.kwargs.get('ExclusiveStartKey') for c in table.query.call_args_list]
        assert starts == [None, {'pk': 'p', 'sk': 'k0'}, {'pk': 'p', 'sk': 'k1'}]

    def test_single_page(self, table):
        table.query.return_value = {'Items': [{'id': 1}]}
        assert permissions_repo.list_team_members('t1') == [{'id': 1}]
        assert table.query.call_count == 1

    def test_non_dict_last_key_never_loops(self, table):
        response = MagicMock()
        response.get.side_effect = lambda k, d=None: [] if k == 'Items' else MagicMock()
        table.query.return_value = response
        assert permissions_repo.list_shared_access('t1') == []
        assert table.query.call_count == 1

    def test_gsi_queries_use_the_index_and_never_scan(self, table):
        table.query.return_value = {'Items': []}
        permissions_repo.list_team_apps('t1')
        permissions_repo.list_apps_shared_with_team('t1')
        permissions_repo.list_user_teams('u1')
        indexes = [c.kwargs['IndexName'] for c in table.query.call_args_list]
        assert indexes == [permissions_repo.TEAM_APPS_INDEX, permissions_repo.TEAM_APPS_INDEX,
                           permissions_repo.USER_TEAMS_INDEX]
        table.scan.assert_not_called()

    def test_list_user_teams_strips_keys_across_pages(self, table):
        table.query.side_effect = _pages(
            [{'pk': 'TEAM#a', 'sk': 'MEMBER#u', 'gsi1pk': 'USER#u', 'gsi1sk': 'TEAM#a', 'team_id': 'a'}],
            [{'pk': 'TEAM#b', 'sk': 'MEMBER#u', 'gsi1pk': 'USER#u', 'gsi1sk': 'TEAM#b', 'team_id': 'b'}],
        )
        assert permissions_repo.list_user_teams('u') == [{'team_id': 'a'}, {'team_id': 'b'}]


class TestTeamNameExists:
    def test_case_insensitive_over_every_page(self, table):
        table.query.side_effect = _pages([{'name': 'Alpha'}], [{'name': 'Beta'}])
        assert permissions_repo.team_name_exists('beta') is True

    def test_absent(self, table):
        table.query.return_value = {'Items': [{'name': 'Alpha'}]}
        assert permissions_repo.team_name_exists('gamma') is False


class TestToDynamo:
    def test_types(self):
        assert permissions_repo.to_dynamo({'s': 'x', 'b': True, 'n': 3, 'l': ['a', 'b']}) == {
            's': {'S': 'x'}, 'b': {'BOOL': True}, 'n': {'N': '3'}, 'l': {'L': [{'S': 'a'}, {'S': 'b'}]},
        }

    def test_bool_is_not_a_number(self):
        assert permissions_repo.to_dynamo({'f': False}) == {'f': {'BOOL': False}}


def test_actor_from_identity():
    assert actor_from_identity({'sub': 's', 'email': 'e@x', 'scope': 'api/admin'}) == {'sub': 's', 'email': 'e@x'}
    assert actor_from_identity({}) == {'sub': '', 'email': ''}
