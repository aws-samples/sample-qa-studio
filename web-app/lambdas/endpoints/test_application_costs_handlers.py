"""Cost read routes (cost allocation, task 6).

``GET /applications/{id}/costs`` → ``{summary, days, usecases}``,
``GET /usecase/{id}/costs`` → ``{summary, days}``,
``GET /dashboard/costs`` → ``{overall, applications}``.

The handlers only read what the collector wrote: the ``USAGE#… / SUMMARY``
items (DynamoDB, through ``FakeTable`` / ``FakeDynamoResource``) and the last
30 rows of a dimension's S3 ledger (through a fake S3 client handed to
``cost_ledger``).  Authorization comes from ``require_resource_access`` /
``filter_visible_apps`` with the owner readers patched by ``authz_test_support``.
"""
import datetime as dt
import io
import json
from typing import Dict, List
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError

import cost_ledger
from application_router import ROUTE_MAP, _match_route
from authz_test_support import APP_ID, TEAM_A, UC_ID, make_event, owned_resources
from cost_ledger import APPLICATION_DIMENSION, USECASE_DIMENSION, ledger_key
from cost_models import (
    OVERALL_DIMENSION_KEY,
    SUMMARY_SK,
    CostSummary,
    LedgerRow,
    ServiceCost,
    application_dimension_key,
    usecase_dimension_key,
)
from fake_table import FakeDynamoResource, FakeTable
from handlers import get_application_costs, get_dashboard_costs, get_usecase_costs

TABLE = 'test-table'
BUCKET = 'test-bucket'
READ_APPS = 'api/applications.read'
READ_USECASES = 'api/usecases.read'
OTHER_APP = 'app-b'
UC_2 = 'uc-2'
UC_3 = 'uc-3'
UC_NO_SUMMARY = 'uc-none'
AS_OF = dt.date(2026, 11, 4)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv('TABLE_NAME', TABLE)
    monkeypatch.setenv('BUCKET_NAME', BUCKET)
    monkeypatch.delenv('S3_BUCKET', raising=False)


# ---------------------------------------------------------------------------
# fakes and records
# ---------------------------------------------------------------------------


class FakeS3:
    """``get_object`` over an in-memory ``key → bytes`` map; a missing key is ``NoSuchKey``."""

    def __init__(self, objects: Dict[str, bytes] = None):
        self.objects = dict(objects or {})
        self.get_calls: List[str] = []

    def get_object(self, Bucket, Key):  # noqa: N803
        self.get_calls.append(Key)
        assert Bucket == BUCKET
        if Key not in self.objects:
            raise ClientError({'Error': {'Code': 'NoSuchKey', 'Message': 'NoSuchKey'}}, 'GetObject')
        return {'Body': io.BytesIO(self.objects[Key]), 'ETag': '"etag"'}


def _row(day: dt.date, cost: float) -> LedgerRow:
    return LedgerRow(date=day, cost=[ServiceCost(service='nova_act', cost=cost, list_cost=cost, usage_seconds=1)],
                     collected_at='2026-11-05T06:00:00Z')


def _ledger(n_days: int, start_cost: float = 1.0) -> bytes:
    rows = [_row(AS_OF - dt.timedelta(days=n_days - 1 - i), start_cost + i) for i in range(n_days)]
    return ''.join(row.model_dump_json() + '\n' for row in rows).encode('utf-8')


def _summary(window_30d: float) -> CostSummary:
    return CostSummary(as_of=AS_OF, window_30d=window_30d, window_30d_list=window_30d, window_1d=window_30d / 30,
                       by_source_30d={'nova_act': window_30d}, days_available=31, updated_at='2026-11-05T06:02:11Z')


def _summary_item(dimension_key: str, window_30d: float) -> dict:
    return _summary(window_30d).to_item(dimension_key)


def _app_metadata(app_id: str, owner_team_id=TEAM_A) -> dict:
    return {'pk': f'APPLICATION#{app_id}', 'sk': 'METADATA', 'id': app_id, 'name': app_id,
            'owner_team_id': owner_team_id}


def _app_index(app_id: str) -> dict:
    return {'pk': 'APPLICATIONS', 'sk': f'APPLICATION#{app_id}', 'id': app_id}


def _association(app_id: str, usecase_id: str) -> dict:
    return {'pk': f'APPLICATION#{app_id}', 'sk': f'USECASE#{usecase_id}', 'associated_at': 't', 'environment': ''}


def _usecase(usecase_id: str, name: str, app_id: str) -> dict:
    return {'pk': 'USECASES', 'sk': f'USECASE#{usecase_id}', 'id': usecase_id, 'name': name,
            'application_id': app_id, 'owner_team_id': TEAM_A}


def _body(response):
    return json.loads(response['body'])


def _full_table() -> FakeTable:
    return FakeTable([
        _app_metadata(APP_ID), _app_index(APP_ID),
        _app_metadata(OTHER_APP), _app_index(OTHER_APP),
        _association(APP_ID, UC_ID), _association(APP_ID, UC_2), _association(APP_ID, UC_3),
        _association(APP_ID, UC_NO_SUMMARY),
        _usecase(UC_ID, 'Login', APP_ID), _usecase(UC_2, 'Checkout', APP_ID), _usecase(UC_3, 'Search', APP_ID),
        _usecase(UC_NO_SUMMARY, 'Brand new', APP_ID),
        _summary_item(application_dimension_key(APP_ID), 42.1),
        _summary_item(application_dimension_key(OTHER_APP), 7.0),
        _summary_item(usecase_dimension_key(UC_ID), 5.0),
        _summary_item(usecase_dimension_key(UC_2), 30.0),
        _summary_item(usecase_dimension_key(UC_3), 7.1),
        _summary_item(OVERALL_DIMENSION_KEY, 99.0),
    ])


@pytest.fixture
def table():
    return _full_table()


@pytest.fixture
def s3(monkeypatch):
    fake = FakeS3({
        ledger_key(APPLICATION_DIMENSION, APP_ID): _ledger(45),
        ledger_key(USECASE_DIMENSION, APP_ID, UC_ID): _ledger(3),
        # History under a previous application: must never be read.
        ledger_key(USECASE_DIMENSION, OTHER_APP, UC_ID): _ledger(40, start_cost=1000.0),
    })
    monkeypatch.setattr(cost_ledger, '_s3_client', fake)
    return fake


def _call(module, table, event, usecase_app=APP_ID):
    """Invoke ``module.handle`` against ``table`` with the owner readers patched."""
    resource = FakeDynamoResource(table, TABLE)
    uc_owner = {'application_id': usecase_app or None, 'owner_team_id': TEAM_A if usecase_app else None,
                'created_by': None}
    with owned_resources(usecase_app=usecase_app or ''), \
            patch('permissions_repo.get_usecase_owner', side_effect=lambda u, include_creator=False: uc_owner), \
            patch.object(module, 'boto3') as boto_mock:
        boto_mock.resource.return_value = resource
        return module.handle(event), resource


# ---------------------------------------------------------------------------
# routing
# ---------------------------------------------------------------------------


class TestRouteMap:
    def test_routes_are_registered(self):
        assert ROUTE_MAP[('GET', '/applications/{id}/costs')] == 'handlers.get_application_costs'
        assert ROUTE_MAP[('GET', '/usecase/{id}/costs')] == 'handlers.get_usecase_costs'
        assert ROUTE_MAP[('GET', '/dashboard/costs')] == 'handlers.get_dashboard_costs'

    def test_no_write_methods_on_cost_routes(self):
        methods = {method for (method, path) in ROUTE_MAP if path.endswith('/costs')}
        assert methods == {'GET'}

    def test_application_costs_is_reached_through_the_proxy_resource(self):
        # /applications/{id}/costs has no explicit API Gateway resource: the router
        # matches the request path against the template and extracts the id.
        module, params = _match_route('GET', '/applications/{proxy+}', f'/applications/{APP_ID}/costs')
        assert (module, params) == ('handlers.get_application_costs', {'id': APP_ID})

    def test_explicit_resources_match_by_resource_template(self):
        assert _match_route('GET', '/usecase/{id}/costs', f'/usecase/{UC_ID}/costs') == \
            ('handlers.get_usecase_costs', {})
        assert _match_route('GET', '/dashboard/costs', '/dashboard/costs') == ('handlers.get_dashboard_costs', {})


# ---------------------------------------------------------------------------
# GET /applications/{id}/costs
# ---------------------------------------------------------------------------


class TestApplicationCosts:
    def _event(self, caller='viewer_a', app_id=APP_ID, scopes=READ_APPS):
        return make_event(caller=caller, path={'id': app_id}, scopes=scopes)

    def test_happy_path_shape(self, table, s3):
        response, _ = _call(get_application_costs, table, self._event())
        assert response['statusCode'] == 200, response['body']
        body = _body(response)
        assert set(body) == {'summary', 'days', 'usecases'}
        assert body['summary'] == _summary(42.1).model_dump(mode='json')
        assert body['summary']['as_of'] == '2026-11-04'
        assert 'pk' not in body['summary'] and 'sk' not in body['summary']

    def test_days_are_the_last_30_ledger_rows_in_date_order(self, table, s3):
        response, _ = _call(get_application_costs, table, self._event())
        days = _body(response)['days']
        assert len(days) == 30
        assert days[0]['date'] == (AS_OF - dt.timedelta(days=29)).isoformat()
        assert days[-1]['date'] == AS_OF.isoformat()
        assert days[-1]['cost'] == [{'service': 'nova_act', 'cost': 45.0, 'list_cost': 45.0,
                                     'usage_seconds': 1.0, 'launches': None}]
        assert s3.get_calls == [ledger_key(APPLICATION_DIMENSION, APP_ID)]

    def test_usecases_sorted_by_window_30d_desc_missing_summary_last(self, table, s3):
        response, _ = _call(get_application_costs, table, self._event())
        usecases = _body(response)['usecases']
        assert [u['usecase_id'] for u in usecases] == [UC_2, UC_3, UC_ID, UC_NO_SUMMARY]
        assert usecases[0] == {'usecase_id': UC_2, 'name': 'Checkout',
                               'summary': _summary(30.0).model_dump(mode='json')}
        assert usecases[-1] == {'usecase_id': UC_NO_SUMMARY, 'name': 'Brand new', 'summary': None}

    def test_usecase_rows_come_from_one_batch_get(self, table, s3):
        _, resource = _call(get_application_costs, table, self._event())
        assert len(resource.batch_get_calls) == 1
        keys = {(k['pk'], k['sk']) for k in resource.batch_get_calls[0]}
        assert (usecase_dimension_key(UC_ID), SUMMARY_SK) in keys
        assert ('USECASES', f'USECASE#{UC_ID}') in keys

    def test_many_usecases_are_batched_in_chunks_of_100_keys(self, s3):
        ids = [f'uc-{i:03d}' for i in range(130)]
        table = FakeTable([_app_metadata(APP_ID)] + [_association(APP_ID, u) for u in ids]
                          + [_usecase(u, u, APP_ID) for u in ids]
                          + [_summary_item(usecase_dimension_key(u), float(i)) for i, u in enumerate(ids)])
        response, resource = _call(get_application_costs, table, self._event())
        assert response['statusCode'] == 200, response['body']
        assert len(_body(response)['usecases']) == 130
        assert all(len(call) <= 100 for call in resource.batch_get_calls)
        assert sum(len(call) for call in resource.batch_get_calls) == 260
        assert _body(response)['usecases'][0]['usecase_id'] == 'uc-129'

    def test_missing_summary_and_ledger_is_200_with_nulls(self, s3):
        table = FakeTable([_app_metadata(APP_ID)])
        del s3.objects[ledger_key(APPLICATION_DIMENSION, APP_ID)]
        response, _ = _call(get_application_costs, table, self._event())
        assert response['statusCode'] == 200, response['body']
        assert _body(response) == {'summary': None, 'days': [], 'usecases': []}

    def test_missing_ledger_file_only(self, table, s3):
        del s3.objects[ledger_key(APPLICATION_DIMENSION, APP_ID)]
        response, _ = _call(get_application_costs, table, self._event())
        body = _body(response)
        assert response['statusCode'] == 200
        assert body['days'] == []
        assert body['summary']['window_30d'] == 42.1

    def test_non_member_is_forbidden_before_any_read(self, table, s3):
        response, resource = _call(get_application_costs, table, self._event(caller='viewer_b'))
        assert response['statusCode'] == 403
        assert resource.batch_get_calls == []
        assert s3.get_calls == []

    def test_missing_scope_is_forbidden(self, table, s3):
        response, _ = _call(get_application_costs, table, self._event(scopes=READ_USECASES))
        assert response['statusCode'] == 403

    def test_s3_failure_is_500(self, table, s3):
        def boom(**_):
            raise ClientError({'Error': {'Code': 'AccessDenied', 'Message': 'denied'}}, 'GetObject')
        s3.get_object = boom
        response, _ = _call(get_application_costs, table, self._event())
        assert response['statusCode'] == 500
        assert 'costs' in _body(response)['error']


# ---------------------------------------------------------------------------
# GET /usecase/{id}/costs
# ---------------------------------------------------------------------------


class TestUsecaseCosts:
    def _event(self, caller='viewer_a', usecase_id=UC_ID, scopes=READ_USECASES):
        return make_event(caller=caller, path={'id': usecase_id}, scopes=scopes)

    def test_happy_path_shape(self, table, s3):
        response, _ = _call(get_usecase_costs, table, self._event())
        assert response['statusCode'] == 200, response['body']
        body = _body(response)
        assert set(body) == {'summary', 'days'}
        assert body['summary'] == _summary(5.0).model_dump(mode='json')
        assert [d['date'] for d in body['days']] == [(AS_OF - dt.timedelta(days=2 - i)).isoformat()
                                                    for i in range(3)]

    def test_reads_the_ledger_under_the_current_application_only(self, table, s3):
        _call(get_usecase_costs, table, self._event())
        assert s3.get_calls == [ledger_key(USECASE_DIMENSION, APP_ID, UC_ID)]

    def test_unassigned_usecase_is_denied_for_members(self, table, s3):
        # An orphan (no application) is admin-only by the resource rule.
        response, _ = _call(get_usecase_costs, table, self._event(), usecase_app=None)
        assert response['statusCode'] == 403

    def test_admin_reads_the_unassigned_ledger_for_an_orphan(self, table, s3):
        s3.objects[ledger_key(USECASE_DIMENSION, None, UC_ID)] = _ledger(2)
        response, _ = _call(get_usecase_costs, table, self._event(caller='admin'), usecase_app=None)
        assert response['statusCode'] == 200, response['body']
        assert s3.get_calls == [ledger_key(USECASE_DIMENSION, None, UC_ID)]
        assert len(_body(response)['days']) == 2

    def test_missing_summary_and_ledger(self, s3):
        table = FakeTable([_usecase(UC_ID, 'Login', APP_ID)])
        del s3.objects[ledger_key(USECASE_DIMENSION, APP_ID, UC_ID)]
        response, _ = _call(get_usecase_costs, table, self._event())
        assert response['statusCode'] == 200, response['body']
        assert _body(response) == {'summary': None, 'days': []}

    def test_non_member_is_forbidden_before_any_read(self, table, s3):
        response, _ = _call(get_usecase_costs, table, self._event(caller='viewer_b'))
        assert response['statusCode'] == 403
        assert s3.get_calls == []

    def test_missing_scope_is_forbidden(self, table, s3):
        response, _ = _call(get_usecase_costs, table, self._event(scopes=READ_APPS))
        assert response['statusCode'] == 403

    def test_shared_view_team_may_read(self, table, s3):
        resource = FakeDynamoResource(table, TABLE)
        uc_owner = {'application_id': APP_ID, 'owner_team_id': TEAM_A, 'created_by': None}
        shares = [{'app_id': APP_ID, 'target_team_id': 'team-b', 'level': 'view'}]
        with owned_resources(shares=shares), \
                patch('permissions_repo.get_usecase_owner', return_value=uc_owner), \
                patch('permissions_repo.list_apps_shared_with_team', return_value=[]), \
                patch.object(get_usecase_costs, 'boto3') as boto_mock:
            boto_mock.resource.return_value = resource
            response = get_usecase_costs.handle(self._event(caller='viewer_b'))
        assert response['statusCode'] == 200, response['body']


# ---------------------------------------------------------------------------
# GET /dashboard/costs
# ---------------------------------------------------------------------------


def _dashboard(table, caller, s3_calls=None, shared=None):
    resource = FakeDynamoResource(table, TABLE)
    with patch('resource_auth.list_apps_shared_with_team', return_value=list(shared or [])), \
            patch.object(get_dashboard_costs, 'boto3') as boto_mock:
        boto_mock.resource.return_value = resource
        return get_dashboard_costs.handle(make_event(caller=caller, scopes=READ_APPS)), resource


class TestDashboardCosts:
    def test_member_sees_own_applications_and_no_overall(self, table, s3):
        table.items[('APPLICATION#app-b', 'METADATA')]['owner_team_id'] = 'team-b'
        response, _ = _dashboard(table, 'viewer_a')
        assert response['statusCode'] == 200, response['body']
        body = _body(response)
        assert set(body) == {'overall', 'applications'}
        assert body['overall'] is None
        assert body['applications'] == [{'application_id': APP_ID,
                                         'summary': _summary(42.1).model_dump(mode='json')}]

    def test_admin_gets_overall_and_every_application(self, table, s3):
        response, _ = _dashboard(table, 'admin')
        body = _body(response)
        assert body['overall'] == _summary(99.0).model_dump(mode='json')
        assert [a['application_id'] for a in body['applications']] == [APP_ID, OTHER_APP]

    def test_admin_without_overall_summary_gets_null(self, table, s3):
        del table.items[(OVERALL_DIMENSION_KEY, SUMMARY_SK)]
        response, _ = _dashboard(table, 'admin')
        assert _body(response)['overall'] is None

    def test_admin_scope_token_counts_as_admin(self, table, s3):
        resource = FakeDynamoResource(table, TABLE)
        event = make_event(caller='no_team', scopes=f'{READ_APPS} api/admin')
        with patch.object(get_dashboard_costs, 'boto3') as boto_mock:
            boto_mock.resource.return_value = resource
            response = get_dashboard_costs.handle(event)
        assert _body(response)['overall'] is not None

    def test_shared_application_is_visible(self, table, s3):
        table.items[('APPLICATION#app-b', 'METADATA')]['owner_team_id'] = 'team-b'
        response, _ = _dashboard(table, 'viewer_a', shared=[{'app_id': OTHER_APP, 'level': 'view'}])
        assert [a['application_id'] for a in _body(response)['applications']] == [APP_ID, OTHER_APP]

    def test_application_without_summary_is_listed_with_null(self, table, s3):
        del table.items[(application_dimension_key(OTHER_APP), SUMMARY_SK)]
        response, _ = _dashboard(table, 'admin')
        rows = {a['application_id']: a['summary'] for a in _body(response)['applications']}
        assert rows[OTHER_APP] is None
        assert rows[APP_ID] is not None

    def test_applications_sorted_by_window_30d_desc(self, table, s3):
        table.items[(application_dimension_key(OTHER_APP), SUMMARY_SK)]['window_30d'] = 500
        response, _ = _dashboard(table, 'admin')
        assert [a['application_id'] for a in _body(response)['applications']] == [OTHER_APP, APP_ID]

    def test_no_team_user_sees_nothing(self, table, s3):
        response, resource = _dashboard(table, 'no_team')
        assert response['statusCode'] == 200
        assert _body(response) == {'overall': None, 'applications': []}

    def test_no_applications_at_all(self, s3):
        response, _ = _dashboard(FakeTable([]), 'admin')
        assert response['statusCode'] == 200
        assert _body(response) == {'overall': None, 'applications': []}

    def test_no_ledger_read(self, table, s3):
        _dashboard(table, 'admin')
        assert s3.get_calls == []

    def test_missing_scope_is_forbidden_before_any_read(self, table, s3):
        resource = FakeDynamoResource(table, TABLE)
        with patch.object(get_dashboard_costs, 'boto3') as boto_mock:
            boto_mock.resource.return_value = resource
            response = get_dashboard_costs.handle(make_event(caller='admin', scopes=READ_USECASES))
        assert response['statusCode'] == 403
        assert resource.batch_get_calls == []

    def test_summaries_are_one_batch_get_per_100_apps(self, s3):
        ids = [f'app-{i:03d}' for i in range(150)]
        table = FakeTable([_app_index(a) for a in ids] + [_app_metadata(a) for a in ids]
                          + [_summary_item(application_dimension_key(a), float(i)) for i, a in enumerate(ids)])
        response, resource = _dashboard(table, 'admin')
        assert response['statusCode'] == 200, response['body']
        assert len(_body(response)['applications']) == 150
        # Metadata batch (150 keys) + summary batch (150 keys), each chunked at 100.
        assert all(len(call) <= 100 for call in resource.batch_get_calls)
        assert sum(len(call) for call in resource.batch_get_calls) == 300
