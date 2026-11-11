"""Cost allocation: the real bill per day (Cost Explorer) and the list price (Pricing API).

Design: ``.kiro/docs/cost-allocation/design.md``.  The collector asks, per day
and per source, what the account was billed (``billed_cost``), or — for
sources whose usage types must be classified client-side, such as MicroVM
compute under ``SERVICE = "AWS Lambda"`` — the bill per ``USAGE_TYPE`` group
(``billed_cost_by_group``; Cost Explorer accepts no ``STARTS_WITH`` filter).
``list_price_per_hour`` turns the Pricing API's per-second OnDemand rate into
the $/h the ``list_cost`` column is computed from.

Both AWS services are global with ``us-east-1`` endpoints; every client is
created there explicitly.  Each ``GetCostAndUsage`` call costs $0.01: callers
make one call per day per source, never one per use case.

No raw API responses are stored or logged (design decision 4b); the warning
paths log the day, the error code and counts only.

Imports pydantic: Lambda entry modules must ``import lambda_init`` first.
"""
import datetime as dt
import json
import logging
from typing import Any, Dict, List, Mapping, Optional

import boto3
from botocore.exceptions import ClientError
from pydantic import BaseModel, Field

from cost_models import SECONDS_PER_HOUR

logger = logging.getLogger(__name__)

#: Cost Explorer, Pricing (and Nova Act) are served from us-east-1 only.
CE_REGION = 'us-east-1'

#: Pricing API ``ServiceCode`` of Nova Act (task 0: ``AmazonNovaAct`` does not exist).
NOVA_ACT_PRICING_SERVICE_CODE = 'NovaAct'

#: The Pricing unit the per-hour list price is derived from.
PRICE_UNIT_SECOND = 'Second'

CE_METRICS = ['UnblendedCost', 'UsageQuantity']
USAGE_TYPE_GROUP_BY = [{'Type': 'DIMENSION', 'Key': 'USAGE_TYPE'}]

#: Cost Explorer raises this until the account has Cost Explorer enabled (~24 h).
DATA_UNAVAILABLE = 'DataUnavailableException'

_ce_client = None
_pricing_client = None
_price_cache: Dict[str, float] = {}


class BilledDay(BaseModel):
    """One day's Cost Explorer line for a filter (or one ``GroupBy`` group)."""

    usd: float = Field(description='UnblendedCost in USD')
    estimated: bool = Field(description='Cost Explorer "Estimated" flag for the day')
    usage_quantity: float = Field(description='UsageQuantity (Nova Act: billed agent seconds)')


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------


def get_ce_client():
    """The module's Cost Explorer client (``us-east-1``), created on first use."""
    global _ce_client
    if _ce_client is None:
        _ce_client = boto3.client('ce', region_name=CE_REGION)
    return _ce_client


def get_pricing_client():
    """The module's Pricing client (``us-east-1``), created on first use."""
    global _pricing_client
    if _pricing_client is None:
        _pricing_client = boto3.client('pricing', region_name=CE_REGION)
    return _pricing_client


# ---------------------------------------------------------------------------
# Cost Explorer
# ---------------------------------------------------------------------------


def service_filter(service: str) -> Dict[str, Any]:
    """Cost Explorer ``Filter`` expression selecting one ``SERVICE`` value (e.g. ``NovaAct``)."""
    if not service or not service.strip():
        raise ValueError('Cost Explorer SERVICE value must not be blank')
    return {'Dimensions': {'Key': 'SERVICE', 'Values': [service], 'MatchOptions': ['EQUALS']}}


def billed_cost(day: dt.date, ce_filter: Mapping[str, Any], *, ce=None) -> Optional[BilledDay]:
    """``GetCostAndUsage`` for one UTC day under ``ce_filter``.

    Returns ``None`` (and logs a warning) on ``DataUnavailableException`` so the
    collector skips the day; any other ``ClientError`` propagates.  A day Cost
    Explorer has no line for is a zero bill, not estimated.
    """
    result = _get_day(day, ce_filter, ce=ce)
    if result is None:
        return None
    return _billed_day(result.get('Total') or {}, _estimated(result))


def billed_cost_by_group(day: dt.date, ce_filter: Mapping[str, Any], *, ce=None) -> Optional[Dict[str, BilledDay]]:
    """``GetCostAndUsage`` for one UTC day grouped by ``USAGE_TYPE``; ``usage type → BilledDay``.

    One call, same price as ``billed_cost``.  Returns ``None`` on
    ``DataUnavailableException``; ``{}`` when the day has no groups.
    """
    result = _get_day(day, ce_filter, ce=ce, GroupBy=USAGE_TYPE_GROUP_BY)
    if result is None:
        return None
    estimated = _estimated(result)
    by_group: Dict[str, BilledDay] = {}
    for group in result.get('Groups') or []:
        keys = group.get('Keys') or []
        if len(keys) != 1:
            raise ValueError(f'Cost Explorer group for {day.isoformat()} has {len(keys)} keys, expected 1')
        by_group[keys[0]] = _billed_day(group.get('Metrics') or {}, estimated)
    return by_group


def _get_day(day: dt.date, ce_filter: Mapping[str, Any], *, ce=None, **extra) -> Optional[Dict[str, Any]]:
    """The single ``ResultsByTime`` entry for ``day``; ``None`` when CE data is unavailable."""
    ce = ce or get_ce_client()
    try:
        response = ce.get_cost_and_usage(
            TimePeriod={'Start': day.isoformat(), 'End': (day + dt.timedelta(days=1)).isoformat()},
            Granularity='DAILY',
            Metrics=list(CE_METRICS),
            Filter=dict(ce_filter),
            **extra,
        )
    except ClientError as e:
        if e.response.get('Error', {}).get('Code') == DATA_UNAVAILABLE:
            logger.warning('Cost Explorer %s for %s: skipping the day', DATA_UNAVAILABLE, day.isoformat())
            return None
        raise
    results = response.get('ResultsByTime') or []
    if len(results) > 1:
        raise ValueError(f'Cost Explorer returned {len(results)} results for {day.isoformat()}, expected 1')
    if not results:
        logger.warning('Cost Explorer returned no result for %s: treating as a zero bill', day.isoformat())
        return {'Total': {}, 'Groups': [], 'Estimated': False}
    return results[0]


def _estimated(result: Mapping[str, Any]) -> bool:
    return bool(result.get('Estimated', False))


def _billed_day(metrics: Mapping[str, Any], estimated: bool) -> BilledDay:
    return BilledDay(
        usd=_amount(metrics, 'UnblendedCost'),
        estimated=estimated,
        usage_quantity=_amount(metrics, 'UsageQuantity'),
    )


def _amount(metrics: Mapping[str, Any], metric: str) -> float:
    return float((metrics.get(metric) or {}).get('Amount') or 0.0)


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------


def list_price_per_hour(service_code: str, *, pricing=None) -> float:
    """List price in USD per hour for ``service_code`` (``NovaAct``: $4.75).

    Picks the ``OnDemand`` price dimension whose ``unit`` is ``Second`` across
    all products of the service and multiplies by 3600.  Raises ``ValueError``
    when no or more than one such dimension exists — never "the first one".
    Results are cached per service code for the life of the process (one
    Pricing call per Lambda invocation); ``clear_price_cache`` resets it.
    """
    if service_code in _price_cache:
        return _price_cache[service_code]
    pricing = pricing or get_pricing_client()
    per_second = _on_demand_rates_per_second(pricing, service_code)
    if len(per_second) != 1:
        raise ValueError(
            f'Pricing {service_code}: expected exactly one OnDemand dimension with unit '
            f'{PRICE_UNIT_SECOND!r}, found {len(per_second)}'
        )
    price = per_second[0] * SECONDS_PER_HOUR
    _price_cache[service_code] = price
    return price


def clear_price_cache() -> None:
    _price_cache.clear()


def _on_demand_rates_per_second(pricing, service_code: str) -> List[float]:
    """Every ``OnDemand`` ``pricePerUnit.USD`` with ``unit == 'Second'`` over all pages of ``GetProducts``."""
    rates: List[float] = []
    kwargs: Dict[str, Any] = {'ServiceCode': service_code}
    while True:
        response = pricing.get_products(**kwargs)
        for price_list_entry in response.get('PriceList') or []:
            product = json.loads(price_list_entry) if isinstance(price_list_entry, str) else price_list_entry
            for term in (product.get('terms') or {}).get('OnDemand', {}).values():
                for dimension in (term.get('priceDimensions') or {}).values():
                    if dimension.get('unit') == PRICE_UNIT_SECOND:
                        rates.append(float(dimension['pricePerUnit']['USD']))
        # Only a real token continues: a MagicMock client answers `.get('NextToken')` with a truthy mock.
        next_token = response.get('NextToken')
        if not isinstance(next_token, str) or not next_token:
            return rates
        kwargs['NextToken'] = next_token
