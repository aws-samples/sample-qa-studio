"""Unit tests for cost_billing: Cost Explorer bill per day and the Pricing list price."""
import datetime as dt
import json
import logging
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

import cost_billing
from cost_billing import (
    CE_REGION,
    NOVA_ACT_PRICING_SERVICE_CODE,
    BilledDay,
    billed_cost,
    billed_cost_by_group,
    list_price_per_hour,
    service_filter,
)

DAY = dt.date(2026, 11, 4)
NOVA_FILTER = {'Dimensions': {'Key': 'SERVICE', 'Values': ['NovaAct'], 'MatchOptions': ['EQUALS']}}


def _client_error(code, operation='GetCostAndUsage'):
    return ClientError({'Error': {'Code': code, 'Message': code}}, operation)


def _metrics(cost, usage):
    return {
        'UnblendedCost': {'Amount': str(cost), 'Unit': 'USD'},
        'UsageQuantity': {'Amount': str(usage), 'Unit': 'N/A'},
    }


def _ce_response(cost='1.42', usage='8124', estimated=True, groups=None):
    result = {
        'TimePeriod': {'Start': DAY.isoformat(), 'End': (DAY + dt.timedelta(days=1)).isoformat()},
        'Estimated': estimated,
    }
    if groups is None:
        result['Total'] = _metrics(cost, usage)
        result['Groups'] = []
    else:
        result['Total'] = {}
        result['Groups'] = [{'Keys': [key], 'Metrics': _metrics(c, u)} for key, c, u in groups]
    return {'ResultsByTime': [result], 'DimensionValueAttributes': []}


@pytest.fixture(autouse=True)
def _reset_module_state():
    cost_billing.clear_price_cache()
    yield
    cost_billing.clear_price_cache()


class TestServiceFilter:
    def test_equals_on_service_dimension(self):
        assert service_filter('NovaAct') == NOVA_FILTER

    def test_rejects_blank_service(self):
        with pytest.raises(ValueError):
            service_filter('')


class TestBilledCost:
    def test_requests_the_single_day_with_both_metrics(self):
        ce = MagicMock()
        ce.get_cost_and_usage.return_value = _ce_response()

        billed_cost(DAY, NOVA_FILTER, ce=ce)

        ce.get_cost_and_usage.assert_called_once_with(
            TimePeriod={'Start': '2026-11-04', 'End': '2026-11-05'},
            Granularity='DAILY',
            Metrics=['UnblendedCost', 'UsageQuantity'],
            Filter=NOVA_FILTER,
        )

    def test_returns_amount_estimated_and_usage_quantity(self):
        ce = MagicMock()
        ce.get_cost_and_usage.return_value = _ce_response(cost='1.42', usage='8124', estimated=True)

        result = billed_cost(DAY, NOVA_FILTER, ce=ce)

        assert result == BilledDay(usd=1.42, estimated=True, usage_quantity=8124.0)

    def test_final_day_is_not_estimated(self):
        ce = MagicMock()
        ce.get_cost_and_usage.return_value = _ce_response(cost='0', usage='0', estimated=False)

        assert billed_cost(DAY, NOVA_FILTER, ce=ce) == BilledDay(usd=0.0, estimated=False, usage_quantity=0.0)

    def test_missing_estimated_flag_counts_as_final(self):
        ce = MagicMock()
        response = _ce_response()
        del response['ResultsByTime'][0]['Estimated']
        ce.get_cost_and_usage.return_value = response

        assert billed_cost(DAY, NOVA_FILTER, ce=ce).estimated is False

    def test_empty_result_is_zero_bill(self, caplog):
        ce = MagicMock()
        ce.get_cost_and_usage.return_value = {'ResultsByTime': []}

        with caplog.at_level(logging.WARNING, logger='cost_billing'):
            result = billed_cost(DAY, NOVA_FILTER, ce=ce)

        assert result == BilledDay(usd=0.0, estimated=False, usage_quantity=0.0)
        assert any('2026-11-04' in record.getMessage() for record in caplog.records)

    def test_more_than_one_result_is_an_error(self):
        ce = MagicMock()
        response = _ce_response()
        response['ResultsByTime'].append(dict(response['ResultsByTime'][0]))
        ce.get_cost_and_usage.return_value = response

        with pytest.raises(ValueError, match='2026-11-04'):
            billed_cost(DAY, NOVA_FILTER, ce=ce)

    def test_data_unavailable_returns_none_and_warns(self, caplog):
        ce = MagicMock()
        ce.get_cost_and_usage.side_effect = _client_error('DataUnavailableException')

        with caplog.at_level(logging.WARNING, logger='cost_billing'):
            result = billed_cost(DAY, NOVA_FILTER, ce=ce)

        assert result is None
        messages = [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]
        assert any('DataUnavailableException' in m and '2026-11-04' in m for m in messages)

    @pytest.mark.parametrize('code', ['AccessDeniedException', 'LimitExceededException', 'ValidationException'])
    def test_other_client_errors_propagate(self, code):
        ce = MagicMock()
        ce.get_cost_and_usage.side_effect = _client_error(code)

        with pytest.raises(ClientError):
            billed_cost(DAY, NOVA_FILTER, ce=ce)

    def test_default_client_is_cost_explorer_in_us_east_1(self, monkeypatch):
        created = {}

        def fake_client(service, **kwargs):
            created[service] = kwargs
            client = MagicMock()
            client.get_cost_and_usage.return_value = _ce_response()
            return client

        monkeypatch.setattr(cost_billing, '_ce_client', None)
        monkeypatch.setattr(cost_billing.boto3, 'client', fake_client)

        billed_cost(DAY, NOVA_FILTER)
        billed_cost(DAY, NOVA_FILTER)

        assert created == {'ce': {'region_name': CE_REGION}}
        assert CE_REGION == 'us-east-1'


class TestBilledCostByGroup:
    def test_groups_by_usage_type_and_returns_one_billed_day_per_group(self):
        ce = MagicMock()
        ce.get_cost_and_usage.return_value = _ce_response(estimated=True, groups=[
            ('EUC1-Lambda-MicroVM-vCPU-Second-ARM', '0.5', '162410'),
            ('EUC1-Lambda-GB-Second', '0.02', '1000'),
        ])
        lambda_filter = service_filter('AWS Lambda')

        result = billed_cost_by_group(DAY, lambda_filter, ce=ce)

        assert result == {
            'EUC1-Lambda-MicroVM-vCPU-Second-ARM': BilledDay(usd=0.5, estimated=True, usage_quantity=162410.0),
            'EUC1-Lambda-GB-Second': BilledDay(usd=0.02, estimated=True, usage_quantity=1000.0),
        }
        ce.get_cost_and_usage.assert_called_once_with(
            TimePeriod={'Start': '2026-11-04', 'End': '2026-11-05'},
            Granularity='DAILY',
            Metrics=['UnblendedCost', 'UsageQuantity'],
            Filter=lambda_filter,
            GroupBy=[{'Type': 'DIMENSION', 'Key': 'USAGE_TYPE'}],
        )

    def test_no_groups_is_an_empty_mapping(self):
        ce = MagicMock()
        ce.get_cost_and_usage.return_value = _ce_response(groups=[])

        assert billed_cost_by_group(DAY, NOVA_FILTER, ce=ce) == {}

    def test_data_unavailable_returns_none(self, caplog):
        ce = MagicMock()
        ce.get_cost_and_usage.side_effect = _client_error('DataUnavailableException')

        with caplog.at_level(logging.WARNING, logger='cost_billing'):
            assert billed_cost_by_group(DAY, NOVA_FILTER, ce=ce) is None

    def test_other_client_errors_propagate(self):
        ce = MagicMock()
        ce.get_cost_and_usage.side_effect = _client_error('AccessDeniedException')

        with pytest.raises(ClientError):
            billed_cost_by_group(DAY, NOVA_FILTER, ce=ce)


def _product(dimensions):
    """A Pricing ``PriceList`` entry (JSON string) with the given OnDemand price dimensions."""
    return json.dumps({
        'product': {'sku': 'NUVWJ3Z7GKC98S2P', 'attributes': {'usagetype': 'USE1-act', 'operation': 'InvokeActStep'}},
        'terms': {'OnDemand': {'NUVWJ3Z7GKC98S2P.JRTCKXETXF': {
            'priceDimensions': {
                f'NUVWJ3Z7GKC98S2P.JRTCKXETXF.{i}': {'unit': unit, 'pricePerUnit': {'USD': usd}}
                for i, (unit, usd) in enumerate(dimensions)
            },
        }}},
    })


class TestListPricePerHour:
    def test_picks_the_second_dimension_and_scales_to_hours(self):
        pricing = MagicMock()
        pricing.get_products.return_value = {'PriceList': [_product([('Second', '0.0013194440')])]}

        price = list_price_per_hour(NOVA_ACT_PRICING_SERVICE_CODE, pricing=pricing)

        assert price == pytest.approx(4.75, abs=1e-5)
        pricing.get_products.assert_called_once_with(ServiceCode='NovaAct')
        assert NOVA_ACT_PRICING_SERVICE_CODE == 'NovaAct'

    def test_ignores_dimensions_with_other_units(self):
        pricing = MagicMock()
        pricing.get_products.return_value = {'PriceList': [
            _product([('Hrs', '99'), ('Second', '0.0013194440'), ('GB', '1')]),
        ]}

        assert list_price_per_hour('NovaAct', pricing=pricing) == pytest.approx(4.75, abs=1e-5)

    def test_no_second_dimension_raises(self):
        pricing = MagicMock()
        pricing.get_products.return_value = {'PriceList': [_product([('Hrs', '4.75')])]}

        with pytest.raises(ValueError, match='NovaAct'):
            list_price_per_hour('NovaAct', pricing=pricing)

    def test_empty_price_list_raises(self):
        pricing = MagicMock()
        pricing.get_products.return_value = {'PriceList': []}

        with pytest.raises(ValueError, match='NovaAct'):
            list_price_per_hour('NovaAct', pricing=pricing)

    def test_more_than_one_second_dimension_raises(self):
        pricing = MagicMock()
        pricing.get_products.return_value = {'PriceList': [
            _product([('Second', '0.001')]),
            _product([('Second', '0.002')]),
        ]}

        with pytest.raises(ValueError, match='2'):
            list_price_per_hour('NovaAct', pricing=pricing)

    def test_reserved_terms_are_ignored(self):
        product = json.loads(_product([('Second', '0.0013194440')]))
        product['terms']['Reserved'] = {'X': {'priceDimensions': {'Y': {'unit': 'Second', 'pricePerUnit': {'USD': '0.0001'}}}}}
        pricing = MagicMock()
        pricing.get_products.return_value = {'PriceList': [json.dumps(product)]}

        assert list_price_per_hour('NovaAct', pricing=pricing) == pytest.approx(4.75, abs=1e-5)

    def test_follows_next_token(self):
        pricing = MagicMock()
        pricing.get_products.side_effect = [
            {'PriceList': [_product([('Hrs', '1')])], 'NextToken': 'page-2'},
            {'PriceList': [_product([('Second', '0.0013194440')])]},
        ]

        assert list_price_per_hour('NovaAct', pricing=pricing) == pytest.approx(4.75, abs=1e-5)
        assert pricing.get_products.call_args_list[1].kwargs == {'ServiceCode': 'NovaAct', 'NextToken': 'page-2'}

    def test_bare_magicmock_next_token_terminates(self):
        pricing = MagicMock()
        pricing.get_products.return_value = {'PriceList': [_product([('Second', '0.0013194440')])],
                                             'NextToken': MagicMock()}

        assert list_price_per_hour('NovaAct', pricing=pricing) == pytest.approx(4.75, abs=1e-5)
        assert pricing.get_products.call_count == 1

    def test_cached_per_service_code(self):
        pricing = MagicMock()
        pricing.get_products.return_value = {'PriceList': [_product([('Second', '0.0013194440')])]}

        first = list_price_per_hour('NovaAct', pricing=pricing)
        second = list_price_per_hour('NovaAct', pricing=pricing)
        list_price_per_hour('OtherCode', pricing=pricing)

        assert first == second
        assert pricing.get_products.call_count == 2
        cost_billing.clear_price_cache()
        list_price_per_hour('NovaAct', pricing=pricing)
        assert pricing.get_products.call_count == 3

    def test_failed_lookup_is_not_cached(self):
        pricing = MagicMock()
        pricing.get_products.side_effect = [
            {'PriceList': []},
            {'PriceList': [_product([('Second', '0.0013194440')])]},
        ]

        with pytest.raises(ValueError):
            list_price_per_hour('NovaAct', pricing=pricing)
        assert list_price_per_hour('NovaAct', pricing=pricing) == pytest.approx(4.75, abs=1e-5)

    def test_client_errors_propagate(self):
        pricing = MagicMock()
        pricing.get_products.side_effect = _client_error('AccessDeniedException', 'GetProducts')

        with pytest.raises(ClientError):
            list_price_per_hour('NovaAct', pricing=pricing)

    def test_default_client_is_pricing_in_us_east_1(self, monkeypatch):
        created = {}

        def fake_client(service, **kwargs):
            created[service] = kwargs
            client = MagicMock()
            client.get_products.return_value = {'PriceList': [_product([('Second', '0.0013194440')])]}
            return client

        monkeypatch.setattr(cost_billing, '_pricing_client', None)
        monkeypatch.setattr(cost_billing.boto3, 'client', fake_client)

        assert list_price_per_hour('NovaAct') == pytest.approx(4.75, abs=1e-5)
        assert created == {'pricing': {'region_name': CE_REGION}}


class TestBilledDayModel:
    def test_round_trips_through_json(self):
        day = BilledDay(usd=1.5, estimated=True, usage_quantity=12.0)
        assert BilledDay.model_validate_json(day.model_dump_json()) == day
