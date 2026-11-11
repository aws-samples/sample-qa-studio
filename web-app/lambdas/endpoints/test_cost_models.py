"""Tests for ``cost_models``: models, ``allocate`` and ``summarize`` (pure, no AWS)."""
import datetime as dt
import json
import math
from decimal import Decimal

import pytest
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from hypothesis import given, settings
from hypothesis import strategies as st

import cost_models
from cost_models import (
    COMPUTE_SERVICE,
    KNOWN_SERVICES,
    NOVA_ACT_SERVICE,
    OVERALL_DIMENSION_KEY,
    SUMMARY_SK,
    TREND_FLAT_BAND_PCT,
    WINDOWS,
    Buckets,
    CollectorRunReport,
    CostSummary,
    LedgerRow,
    ServiceCost,
    SkippedDay,
    UsecaseMeta,
    allocate,
    application_dimension_key,
    summarize,
    usecase_dimension_key,
    workflow_name_to_usecase_id,
)

DAY = dt.date(2026, 11, 4)
COLLECTED_AT = '2026-11-05T06:02:11Z'
UPDATED_AT = '2026-11-05T06:02:12Z'
ABS_TOL = 1e-6

META = {
    'u-a1': {'application_id': 'app-a', 'name': 'Login'},
    'u-a2': {'application_id': 'app-a', 'name': 'Checkout'},
    'u-b1': {'application_id': 'app-b', 'name': 'Search'},
    'u-none': {'application_id': None, 'name': 'Orphan'},
}


def _allocate(**overrides):
    kwargs = dict(
        day=DAY,
        billed_by_source={NOVA_ACT_SERVICE: (10.0, True)},
        list_price_by_source={NOVA_ACT_SERVICE: 4.75},
        usage_by_source={NOVA_ACT_SERVICE: {'u-a1': 3600.0, 'u-a2': 1800.0, 'u-b1': 1800.0, 'u-none': 1800.0}},
        launches_by_usecase={},
        usecase_meta=META,
        collected_at=COLLECTED_AT,
    )
    kwargs.update(overrides)
    return allocate(**kwargs)


def _cost(row: LedgerRow, service: str) -> ServiceCost:
    return next(c for c in row.cost if c.service == service)


# ---------------------------------------------------------------------------
# Constants and helpers
# ---------------------------------------------------------------------------


def test_constants_match_design():
    assert TREND_FLAT_BAND_PCT == 5.0
    assert WINDOWS == (1, 7, 30)
    assert KNOWN_SERVICES == ('nova_act', 'compute')
    assert OVERALL_DIMENSION_KEY == 'USAGE#OVERALL'
    assert SUMMARY_SK == 'SUMMARY'
    assert application_dimension_key('app-1') == 'USAGE#APPLICATION#app-1'
    assert usecase_dimension_key('uc-1') == 'USAGE#USECASE#uc-1'


def test_workflow_name_to_usecase_id_is_identity_for_uuid7():
    uid = '0192f3a4-5b6c-7d8e-9f01-23456789abcd'
    assert workflow_name_to_usecase_id(uid) == uid
    assert workflow_name_to_usecase_id('legacy-name') == 'legacy-name'


def test_summary_model_has_every_window_field():
    """The flat fields are declared explicitly; this guards them against WINDOWS drift."""
    for w in WINDOWS:
        for suffix in ('', '_list', '_trend', '_change_pct'):
            assert f'window_{w}d{suffix}' in CostSummary.model_fields


# ---------------------------------------------------------------------------
# allocate — examples
# ---------------------------------------------------------------------------


def test_allocate_returns_usecase_application_and_overall_rows():
    rows = _allocate()
    assert set(rows) == {
        usecase_dimension_key('u-a1'), usecase_dimension_key('u-a2'),
        usecase_dimension_key('u-b1'), usecase_dimension_key('u-none'),
        application_dimension_key('app-a'), application_dimension_key('app-b'),
        OVERALL_DIMENSION_KEY,
    }
    for row in rows.values():
        assert row.date == DAY
        assert row.estimated is True
        assert row.collected_at == COLLECTED_AT


def test_allocate_splits_bill_proportionally_to_usage():
    rows = _allocate()
    # 9000 s total; u-a1 has 3600 s → 40 %
    a1 = _cost(rows[usecase_dimension_key('u-a1')], NOVA_ACT_SERVICE)
    assert a1.cost == pytest.approx(4.0)
    assert a1.list_cost == pytest.approx(4.75)
    assert a1.usage_seconds == 3600.0
    assert a1.launches is None
    a2 = _cost(rows[usecase_dimension_key('u-a2')], NOVA_ACT_SERVICE)
    assert a2.cost == pytest.approx(2.0)
    assert a2.list_cost == pytest.approx(2.375)


def test_allocate_usecase_rows_carry_application_id_and_no_buckets():
    rows = _allocate()
    assert rows[usecase_dimension_key('u-a1')].application_id == 'app-a'
    assert rows[usecase_dimension_key('u-none')].application_id is None
    assert rows[usecase_dimension_key('u-a1')].buckets is None


def test_allocate_application_rows_sum_their_usecases_with_zero_buckets():
    rows = _allocate()
    app_a = rows[application_dimension_key('app-a')]
    assert app_a.application_id is None
    assert _cost(app_a, NOVA_ACT_SERVICE).cost == pytest.approx(6.0)
    assert _cost(app_a, NOVA_ACT_SERVICE).usage_seconds == 5400.0
    assert app_a.buckets == Buckets()


def test_allocate_overall_row_buckets():
    rows = _allocate()
    overall = rows[OVERALL_DIMENSION_KEY]
    assert overall.application_id is None
    assert _cost(overall, NOVA_ACT_SERVICE).cost == pytest.approx(10.0)
    assert overall.buckets.unassigned == pytest.approx(2.0)   # u-none
    assert overall.buckets.unallocated == pytest.approx(0.0)
    assert overall.buckets.unmetered == pytest.approx(0.0)


def test_allocate_unknown_workflow_goes_to_unallocated():
    rows = _allocate(usage_by_source={NOVA_ACT_SERVICE: {'u-a1': 3600.0, 'ghost': 3600.0}})
    assert usecase_dimension_key('ghost') not in rows
    overall = rows[OVERALL_DIMENSION_KEY]
    assert overall.buckets.unallocated == pytest.approx(5.0)
    assert _cost(overall, NOVA_ACT_SERVICE).cost == pytest.approx(5.0)
    assert _cost(overall, NOVA_ACT_SERVICE).usage_seconds == 3600.0


def test_allocate_no_usage_puts_whole_bill_in_unmetered():
    rows = _allocate(usage_by_source={})
    assert set(rows) == {OVERALL_DIMENSION_KEY}
    overall = rows[OVERALL_DIMENSION_KEY]
    assert overall.buckets.unmetered == pytest.approx(10.0)
    assert _cost(overall, NOVA_ACT_SERVICE).cost == 0.0
    assert overall.total() == 0.0


def test_allocate_zero_usage_entries_yield_zero_cost_rows():
    rows = _allocate(usage_by_source={NOVA_ACT_SERVICE: {'u-a1': 0.0}})
    assert _cost(rows[usecase_dimension_key('u-a1')], NOVA_ACT_SERVICE).cost == 0.0
    assert rows[OVERALL_DIMENSION_KEY].buckets.unmetered == pytest.approx(10.0)


def test_allocate_source_without_bill_costs_nothing_but_keeps_usage_and_list_price():
    rows = _allocate(billed_by_source={}, list_price_by_source={NOVA_ACT_SERVICE: 4.75})
    a1 = _cost(rows[usecase_dimension_key('u-a1')], NOVA_ACT_SERVICE)
    assert a1.cost == 0.0
    assert a1.list_cost == pytest.approx(4.75)
    assert rows[OVERALL_DIMENSION_KEY].estimated is False
    assert rows[OVERALL_DIMENSION_KEY].buckets.unmetered == 0.0


def test_allocate_missing_list_price_defaults_to_zero():
    rows = _allocate(list_price_by_source={})
    assert _cost(rows[usecase_dimension_key('u-a1')], NOVA_ACT_SERVICE).list_cost == 0.0


def test_allocate_every_row_lists_every_source_in_sorted_order():
    rows = _allocate(
        billed_by_source={NOVA_ACT_SERVICE: (10.0, False), COMPUTE_SERVICE: (1.0, True)},
        usage_by_source={NOVA_ACT_SERVICE: {'u-a1': 3600.0}, COMPUTE_SERVICE: {'u-b1': 60.0}},
        launches_by_usecase={'u-b1': 3},
    )
    for row in rows.values():
        assert [c.service for c in row.cost] == sorted([COMPUTE_SERVICE, NOVA_ACT_SERVICE])
        assert row.estimated is True
    a1 = rows[usecase_dimension_key('u-a1')]
    assert _cost(a1, COMPUTE_SERVICE).cost == 0.0
    assert _cost(a1, COMPUTE_SERVICE).launches == 0
    assert _cost(a1, NOVA_ACT_SERVICE).launches is None
    b1 = rows[usecase_dimension_key('u-b1')]
    assert _cost(b1, COMPUTE_SERVICE).cost == pytest.approx(1.0)
    assert _cost(b1, COMPUTE_SERVICE).launches == 3
    assert _cost(rows[OVERALL_DIMENSION_KEY], COMPUTE_SERVICE).launches == 3
    assert _cost(rows[application_dimension_key('app-a')], COMPUTE_SERVICE).launches == 0


def test_allocate_accepts_usecase_meta_models():
    rows = _allocate(usecase_meta={'u-a1': UsecaseMeta(application_id='app-a', name='Login')},
                     usage_by_source={NOVA_ACT_SERVICE: {'u-a1': 10.0}})
    assert rows[usecase_dimension_key('u-a1')].application_id == 'app-a'
    assert application_dimension_key('app-a') in rows


def test_allocate_empty_application_id_is_unassigned():
    rows = _allocate(usecase_meta={'u-a1': {'application_id': '', 'name': 'x'}},
                     usage_by_source={NOVA_ACT_SERVICE: {'u-a1': 10.0}})
    assert rows[usecase_dimension_key('u-a1')].application_id is None
    assert rows[OVERALL_DIMENSION_KEY].buckets.unassigned == pytest.approx(10.0)
    assert not any(k.startswith('USAGE#APPLICATION#') for k in rows)


def test_allocate_defaults_collected_at_to_utc_now():
    rows = allocate(DAY, {}, {}, {}, {}, {})
    collected_at = rows[OVERALL_DIMENSION_KEY].collected_at
    assert collected_at.endswith('Z')
    parsed = dt.datetime.fromisoformat(collected_at.replace('Z', '+00:00'))
    assert abs((dt.datetime.now(dt.timezone.utc) - parsed).total_seconds()) < 60


def test_allocate_is_deterministic():
    assert _allocate() == _allocate()
    assert [r.model_dump_json() for r in _allocate().values()] == [r.model_dump_json() for r in _allocate().values()]


# ---------------------------------------------------------------------------
# allocate — invariants (hypothesis)
# ---------------------------------------------------------------------------

USECASE_IDS = ['u0', 'u1', 'u2', 'u3', 'u4']
GHOST_IDS = ['ghost0', 'ghost1']
APP_IDS = [None, 'app0', 'app1', 'app2']
money = st.floats(min_value=0.0, max_value=10_000.0, allow_nan=False, allow_infinity=False)
# Subnormal seconds (5e-324) are not realistic usage and make billed × seconds underflow before the division.
seconds = st.floats(min_value=0.0, max_value=100_000.0, allow_nan=False, allow_infinity=False,
                    allow_subnormal=False)
sources = st.lists(st.sampled_from(list(KNOWN_SERVICES)), min_size=1, max_size=2, unique=True)


@st.composite
def allocation_inputs(draw):
    srcs = draw(sources)
    billed = {s: (draw(money), draw(st.booleans())) for s in srcs if draw(st.booleans())}
    prices = {s: draw(st.floats(min_value=0.0, max_value=10.0)) for s in srcs}
    usage = {}
    for s in srcs:
        keys = draw(st.lists(st.sampled_from(USECASE_IDS + GHOST_IDS), unique=True))
        usage[s] = {k: draw(seconds) for k in keys}
    launches = {u: draw(st.integers(min_value=0, max_value=20)) for u in USECASE_IDS}
    meta = {u: {'application_id': draw(st.sampled_from(APP_IDS)), 'name': u} for u in USECASE_IDS}
    return billed, prices, usage, launches, meta


def _rows_by_kind(rows):
    usecases = {k: r for k, r in rows.items() if k.startswith('USAGE#USECASE#')}
    apps = {k: r for k, r in rows.items() if k.startswith('USAGE#APPLICATION#')}
    return usecases, apps, rows[OVERALL_DIMENSION_KEY]


@settings(max_examples=200)
@given(allocation_inputs())
def test_property_rows_plus_buckets_equal_the_bill(inputs):
    billed, prices, usage, launches, meta = inputs
    rows = allocate(DAY, billed, prices, usage, launches, meta, collected_at=COLLECTED_AT)
    usecases, _apps, overall = _rows_by_kind(rows)
    total_billed = sum(usd for usd, _ in billed.values())
    allocated = sum(r.total() for r in usecases.values())
    assert math.isclose(allocated + overall.buckets.unallocated + overall.buckets.unmetered,
                        total_billed, abs_tol=ABS_TOL)
    # per source: Σ usecase cost == overall cost for that source
    for service in {c.service for c in overall.cost}:
        assert math.isclose(sum(_cost(r, service).cost for r in usecases.values()),
                            _cost(overall, service).cost, abs_tol=ABS_TOL)


@settings(max_examples=200)
@given(st.sampled_from(list(KNOWN_SERVICES)), money, st.booleans(),
       st.dictionaries(st.sampled_from(USECASE_IDS + GHOST_IDS), seconds))
def test_property_single_source_sum_equals_bill(service, usd, estimated, usage):
    meta = {u: {'application_id': 'app', 'name': u} for u in USECASE_IDS}
    rows = allocate(DAY, {service: (usd, estimated)}, {service: 4.75}, {service: usage}, {}, meta,
                    collected_at=COLLECTED_AT)
    usecases, _apps, overall = _rows_by_kind(rows)
    allocated = sum(_cost(r, service).cost for r in usecases.values())
    assert math.isclose(allocated + overall.buckets.unallocated + overall.buckets.unmetered, usd, abs_tol=ABS_TOL)
    if sum(usage.values()) == 0:
        assert allocated == 0.0
        assert overall.buckets.unallocated == 0.0
        assert math.isclose(overall.buckets.unmetered, usd, abs_tol=ABS_TOL)
    else:
        assert math.isclose(overall.buckets.unmetered, 0.0, abs_tol=ABS_TOL)


@settings(max_examples=200)
@given(allocation_inputs())
def test_property_buckets_and_costs_are_non_negative(inputs):
    billed, prices, usage, launches, meta = inputs
    rows = allocate(DAY, billed, prices, usage, launches, meta, collected_at=COLLECTED_AT)
    for row in rows.values():
        for c in row.cost:
            assert c.cost >= 0.0
            assert c.list_cost >= 0.0
            assert c.usage_seconds >= 0.0
        if row.buckets is not None:
            assert row.buckets.unassigned >= 0.0
            assert row.buckets.unallocated >= 0.0
            assert row.buckets.unmetered >= 0.0


@settings(max_examples=200)
@given(allocation_inputs())
def test_property_list_cost_is_usage_hours_times_price(inputs):
    billed, prices, usage, launches, meta = inputs
    rows = allocate(DAY, billed, prices, usage, launches, meta, collected_at=COLLECTED_AT)
    for row in rows.values():
        for c in row.cost:
            assert math.isclose(c.list_cost, c.usage_seconds / 3600.0 * prices[c.service], rel_tol=1e-9, abs_tol=1e-9)


@settings(max_examples=200)
@given(allocation_inputs())
def test_property_overall_equals_applications_plus_unassigned(inputs):
    billed, prices, usage, launches, meta = inputs
    rows = allocate(DAY, billed, prices, usage, launches, meta, collected_at=COLLECTED_AT)
    usecases, apps, overall = _rows_by_kind(rows)
    assert math.isclose(sum(r.total() for r in apps.values()) + overall.buckets.unassigned,
                        overall.total(), abs_tol=ABS_TOL)
    for service in {c.service for c in overall.cost}:
        app_sum = sum(_cost(r, service).cost for r in apps.values())
        unassigned = sum(_cost(r, service).cost for r in usecases.values() if r.application_id is None)
        assert math.isclose(app_sum + unassigned, _cost(overall, service).cost, abs_tol=ABS_TOL)
        assert math.isclose(sum(_cost(r, service).usage_seconds for r in apps.values())
                            + sum(_cost(r, service).usage_seconds for r in usecases.values()
                                  if r.application_id is None),
                            _cost(overall, service).usage_seconds, rel_tol=1e-9, abs_tol=1e-6)
    for app_key, app_row in apps.items():
        app_id = app_key[len('USAGE#APPLICATION#'):]
        members = [r for r in usecases.values() if r.application_id == app_id]
        assert members
        assert math.isclose(sum(r.total() for r in members), app_row.total(), abs_tol=ABS_TOL)


@settings(max_examples=100)
@given(allocation_inputs())
def test_property_no_usage_means_no_cost_and_unmetered_bill(inputs):
    billed, prices, _usage, launches, meta = inputs
    zero_usage = {s: {u: 0.0 for u in USECASE_IDS} for s in billed}
    rows = allocate(DAY, billed, prices, zero_usage, launches, meta, collected_at=COLLECTED_AT)
    for row in rows.values():
        assert row.total() == 0.0
    total_billed = sum(usd for usd, _ in billed.values())
    assert math.isclose(rows[OVERALL_DIMENSION_KEY].buckets.unmetered, total_billed, abs_tol=ABS_TOL)


# ---------------------------------------------------------------------------
# allocate — compute: VM seconds + launch count (task 12)
# ---------------------------------------------------------------------------


def _allocate_compute(**overrides):
    kwargs = dict(
        billed_by_source={COMPUTE_SERVICE: (6.0, False)},                 # compute usage types (vCPU-s, GB-s)
        launch_billed_by_source={COMPUTE_SERVICE: 2.0},                   # snapshot usage types
        list_price_by_source={},
        usage_by_source={COMPUTE_SERVICE: {'u-a1': 900.0, 'u-b1': 300.0}},
        launches_by_usecase={'u-a1': 1, 'u-b1': 3},
    )
    kwargs.update(overrides)
    return _allocate(**kwargs)


def test_allocate_compute_splits_seconds_bill_and_launch_bill_separately():
    rows = _allocate_compute()
    a1 = _cost(rows[usecase_dimension_key('u-a1')], COMPUTE_SERVICE)
    b1 = _cost(rows[usecase_dimension_key('u-b1')], COMPUTE_SERVICE)
    # seconds: 6.0 × 900/1200 = 4.5, launches: 2.0 × 1/4 = 0.5
    assert a1.cost == pytest.approx(5.0)
    assert a1.usage_seconds == 900.0 and a1.launches == 1
    # seconds: 6.0 × 300/1200 = 1.5, launches: 2.0 × 3/4 = 1.5
    assert b1.cost == pytest.approx(3.0)
    assert b1.launches == 3
    overall = rows[OVERALL_DIMENSION_KEY]
    assert _cost(overall, COMPUTE_SERVICE).cost == pytest.approx(8.0)
    assert _cost(overall, COMPUTE_SERVICE).launches == 4
    assert overall.buckets.unmetered == pytest.approx(0.0)
    assert overall.total() == pytest.approx(8.0)


def test_allocate_compute_launch_only_usecase_gets_a_row_with_the_launch_share():
    """A use case whose only VM is still running has a launch but no seconds yet."""
    rows = _allocate_compute(usage_by_source={COMPUTE_SERVICE: {'u-a1': 900.0}},
                             launches_by_usecase={'u-a1': 1, 'u-b1': 1})
    b1 = _cost(rows[usecase_dimension_key('u-b1')], COMPUTE_SERVICE)
    assert b1.usage_seconds == 0.0
    assert b1.launches == 1
    assert b1.cost == pytest.approx(1.0)        # half of the 2.0 launch-keyed bill
    a1 = _cost(rows[usecase_dimension_key('u-a1')], COMPUTE_SERVICE)
    assert a1.cost == pytest.approx(6.0 + 1.0)
    assert rows[OVERALL_DIMENSION_KEY].buckets.unmetered == pytest.approx(0.0)


def test_allocate_compute_zero_launches_puts_launch_bill_in_unmetered():
    rows = _allocate_compute(launches_by_usecase={})
    overall = rows[OVERALL_DIMENSION_KEY]
    assert overall.buckets.unmetered == pytest.approx(2.0)
    assert _cost(overall, COMPUTE_SERVICE).cost == pytest.approx(6.0)
    assert _cost(overall, COMPUTE_SERVICE).launches == 0


def test_allocate_compute_zero_seconds_puts_seconds_bill_in_unmetered():
    rows = _allocate_compute(usage_by_source={})
    overall = rows[OVERALL_DIMENSION_KEY]
    assert overall.buckets.unmetered == pytest.approx(6.0)
    assert _cost(overall, COMPUTE_SERVICE).cost == pytest.approx(2.0)
    assert _cost(overall, COMPUTE_SERVICE).usage_seconds == 0.0


def test_allocate_compute_launches_of_unknown_usecase_are_unallocated():
    rows = _allocate_compute(launches_by_usecase={'u-a1': 1, 'ghost': 1})
    overall = rows[OVERALL_DIMENSION_KEY]
    assert usecase_dimension_key('ghost') not in rows
    assert overall.buckets.unallocated == pytest.approx(1.0)
    assert _cost(overall, COMPUTE_SERVICE).launches == 1
    assert overall.buckets.unmetered == pytest.approx(0.0)


def test_allocate_launch_bill_without_launch_bill_mapping_is_the_old_behaviour():
    with_none = _allocate(billed_by_source={COMPUTE_SERVICE: (6.0, False)},
                          usage_by_source={COMPUTE_SERVICE: {'u-a1': 900.0}}, launches_by_usecase={'u-a1': 2})
    with_empty = _allocate(billed_by_source={COMPUTE_SERVICE: (6.0, False)},
                           usage_by_source={COMPUTE_SERVICE: {'u-a1': 900.0}}, launches_by_usecase={'u-a1': 2},
                           launch_billed_by_source={})
    assert with_none == with_empty
    assert _cost(with_none[usecase_dimension_key('u-a1')], COMPUTE_SERVICE).cost == pytest.approx(6.0)


def test_allocate_launch_bill_for_a_non_compute_source_is_rejected():
    with pytest.raises(ValueError, match='launch'):
        _allocate(launch_billed_by_source={NOVA_ACT_SERVICE: 1.0})


def test_allocate_launch_bill_alone_makes_the_source_appear_on_every_row():
    rows = _allocate(launch_billed_by_source={COMPUTE_SERVICE: 2.0})
    for row in rows.values():
        assert [c.service for c in row.cost] == [COMPUTE_SERVICE, NOVA_ACT_SERVICE]
    assert rows[OVERALL_DIMENSION_KEY].buckets.unmetered == pytest.approx(2.0)


@settings(max_examples=200)
@given(money, money, st.dictionaries(st.sampled_from(USECASE_IDS + GHOST_IDS), seconds),
       st.dictionaries(st.sampled_from(USECASE_IDS + GHOST_IDS), st.integers(min_value=0, max_value=20)))
def test_property_compute_both_parts_sum_to_the_bill(seconds_usd, launch_usd, usage, launches):
    meta = {u: {'application_id': 'app', 'name': u} for u in USECASE_IDS}
    rows = allocate(DAY, {COMPUTE_SERVICE: (seconds_usd, False)}, {}, {COMPUTE_SERVICE: usage}, launches, meta,
                    launch_billed_by_source={COMPUTE_SERVICE: launch_usd}, collected_at=COLLECTED_AT)
    usecases, _apps, overall = _rows_by_kind(rows)
    allocated = sum(_cost(r, COMPUTE_SERVICE).cost for r in usecases.values())
    assert math.isclose(allocated + overall.buckets.unallocated + overall.buckets.unmetered,
                        seconds_usd + launch_usd, abs_tol=ABS_TOL)
    assert _cost(overall, COMPUTE_SERVICE).launches == sum(n for u, n in launches.items() if u in meta)
    expected_unmetered = (seconds_usd if sum(usage.values()) == 0 else 0.0) + \
        (launch_usd if sum(launches.values()) == 0 else 0.0)
    assert math.isclose(overall.buckets.unmetered, expected_unmetered, abs_tol=ABS_TOL)
    for row in rows.values():
        for c in row.cost:
            assert c.cost >= 0.0


# ---------------------------------------------------------------------------
# summarize
# ---------------------------------------------------------------------------


def _row(day: dt.date, cost: float, list_cost: float = 0.0, estimated: bool = False,
         compute: float = 0.0) -> LedgerRow:
    services = [ServiceCost(service=NOVA_ACT_SERVICE, cost=cost, list_cost=list_cost, usage_seconds=cost * 10)]
    if compute:
        services.append(ServiceCost(service=COMPUTE_SERVICE, cost=compute, list_cost=compute, usage_seconds=1,
                                    launches=1))
    return LedgerRow(date=day, estimated=estimated, cost=services, buckets=Buckets(), collected_at=COLLECTED_AT)


def _daily_rows(as_of: dt.date, days: int, cost_for_day) -> list:
    return [_row(as_of - dt.timedelta(days=i), cost_for_day(i)) for i in range(days)]


def test_summarize_empty_rows():
    summary = summarize([], DAY, updated_at=UPDATED_AT)
    assert summary.as_of == DAY
    assert summary.days_available == 0
    assert summary.estimated_days == 0
    assert summary.by_source_30d == {}
    assert summary.updated_at == UPDATED_AT
    for w in WINDOWS:
        assert getattr(summary, f'window_{w}d') == 0.0
        assert getattr(summary, f'window_{w}d_list') == 0.0
        assert getattr(summary, f'window_{w}d_trend') is None
        assert getattr(summary, f'window_{w}d_change_pct') is None


def test_summarize_windows_sum_the_right_days():
    # cost of the day as_of - i is (i + 1); 60 days of data
    rows = _daily_rows(DAY, 60, lambda i: float(i + 1))
    summary = summarize(rows, DAY, updated_at=UPDATED_AT)
    assert summary.window_1d == 1.0
    assert summary.window_7d == sum(range(1, 8))      # 28
    assert summary.window_30d == sum(range(1, 31))    # 465
    assert summary.days_available == 60
    # previous windows: 1d → 2; 7d → 8..14 = 77; 30d → 31..60 = 1365
    assert summary.window_1d_change_pct == pytest.approx((1 - 2) / 2 * 100)
    assert summary.window_7d_change_pct == pytest.approx((28 - 77) / 77 * 100)
    assert summary.window_30d_change_pct == pytest.approx((465 - 1365) / 1365 * 100)
    assert summary.window_1d_trend == 'down'
    assert summary.window_7d_trend == 'down'
    assert summary.window_30d_trend == 'down'


def test_summarize_list_windows_and_by_source():
    rows = [_row(DAY - dt.timedelta(days=i), cost=1.0, list_cost=2.0, compute=0.5) for i in range(40)]
    summary = summarize(rows, DAY, updated_at=UPDATED_AT)
    assert summary.window_1d == pytest.approx(1.5)
    assert summary.window_1d_list == pytest.approx(2.5)
    assert summary.window_7d_list == pytest.approx(7 * 2.5)
    assert summary.window_30d_list == pytest.approx(30 * 2.5)
    assert summary.by_source_30d == {NOVA_ACT_SERVICE: pytest.approx(30.0), COMPUTE_SERVICE: pytest.approx(15.0)}


def test_summarize_trend_requires_two_windows_of_data():
    rows = _daily_rows(DAY, 14, lambda i: 1.0)
    summary = summarize(rows, DAY, updated_at=UPDATED_AT)
    assert summary.days_available == 14
    assert summary.window_1d_trend == 'flat'
    assert summary.window_7d_trend == 'flat'
    assert summary.window_30d_trend is None
    assert summary.window_30d_change_pct is None   # previous window is 0
    assert summary.window_30d == 14.0
    rows = _daily_rows(DAY, 13, lambda i: 1.0)
    assert summarize(rows, DAY, updated_at=UPDATED_AT).window_7d_trend is None
    assert summarize(rows[:1], DAY, updated_at=UPDATED_AT).window_1d_trend is None


def test_summarize_missing_dates_count_zero_but_not_available():
    rows = [_row(DAY, 3.0), _row(DAY - dt.timedelta(days=5), 2.0)]
    summary = summarize(rows, DAY, updated_at=UPDATED_AT)
    assert summary.days_available == 2
    assert summary.window_1d == 3.0
    assert summary.window_7d == 5.0
    # 2 rows ≥ 2·1 → the 1d trend is computed; the missing previous day counts as 0
    assert summary.window_1d_change_pct is None
    assert summary.window_1d_trend == 'up'
    # 2 rows < 2·7 → not enough data
    assert summary.window_7d_trend is None
    assert summary.window_7d_change_pct is None


def test_summarize_trend_when_previous_is_zero():
    # 2 rows available for the 1d window: previous (yesterday) is 0 → change_pct null, trend up
    rows = [_row(DAY, 3.0), _row(DAY - dt.timedelta(days=1), 0.0)]
    summary = summarize(rows, DAY, updated_at=UPDATED_AT)
    assert summary.window_1d_change_pct is None
    assert summary.window_1d_trend == 'up'
    rows = [_row(DAY, 0.0), _row(DAY - dt.timedelta(days=1), 0.0)]
    summary = summarize(rows, DAY, updated_at=UPDATED_AT)
    assert summary.window_1d_change_pct is None
    assert summary.window_1d_trend == 'flat'


@pytest.mark.parametrize('current,previous,expected', [
    (100.0 + TREND_FLAT_BAND_PCT, 100.0, 'flat'),           # exactly on the band → flat
    (100.0 + TREND_FLAT_BAND_PCT + 0.01, 100.0, 'up'),
    (100.0 - TREND_FLAT_BAND_PCT, 100.0, 'flat'),
    (100.0 - TREND_FLAT_BAND_PCT - 0.01, 100.0, 'down'),
    (100.0, 100.0, 'flat'),
])
def test_summarize_dead_band(current, previous, expected):
    rows = [_row(DAY, current), _row(DAY - dt.timedelta(days=1), previous)]
    summary = summarize(rows, DAY, updated_at=UPDATED_AT)
    assert summary.window_1d_trend == expected
    assert summary.window_1d_change_pct == pytest.approx((current - previous) / previous * 100)


def test_summarize_estimated_days_counts_only_the_30d_window():
    rows = [_row(DAY - dt.timedelta(days=i), 1.0, estimated=(i in (0, 1, 35))) for i in range(40)]
    summary = summarize(rows, DAY, updated_at=UPDATED_AT)
    assert summary.estimated_days == 2


def test_summarize_ignores_rows_after_as_of():
    rows = [_row(DAY + dt.timedelta(days=1), 99.0), _row(DAY, 1.0)]
    summary = summarize(rows, DAY, updated_at=UPDATED_AT)
    assert summary.window_1d == 1.0
    assert summary.window_30d == 1.0
    assert summary.days_available == 1


def test_summarize_rejects_duplicate_dates():
    with pytest.raises(ValueError, match='2026-11-04'):
        summarize([_row(DAY, 1.0), _row(DAY, 2.0)], DAY)


def test_summarize_accepts_unsorted_rows():
    rows = _daily_rows(DAY, 10, lambda i: float(i))
    assert summarize(list(reversed(rows)), DAY, updated_at=UPDATED_AT) == summarize(rows, DAY, updated_at=UPDATED_AT)


def test_summarize_defaults_updated_at_to_utc_now():
    summary = summarize([], DAY)
    assert summary.updated_at.endswith('Z')
    parsed = dt.datetime.fromisoformat(summary.updated_at.replace('Z', '+00:00'))
    assert abs((dt.datetime.now(dt.timezone.utc) - parsed).total_seconds()) < 60


@settings(max_examples=100)
@given(st.lists(st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
                min_size=0, max_size=70))
def test_property_summarize_windows_are_consistent(costs):
    rows = [_row(DAY - dt.timedelta(days=i), c) for i, c in enumerate(costs)]
    summary = summarize(rows, DAY, updated_at=UPDATED_AT)
    assert summary.days_available == len(costs)
    assert summary.window_1d <= summary.window_7d + ABS_TOL <= summary.window_30d + 2 * ABS_TOL
    assert math.isclose(summary.window_30d, sum(costs[:30]), abs_tol=ABS_TOL)
    assert math.isclose(sum(summary.by_source_30d.values()), summary.window_30d, abs_tol=ABS_TOL)
    for w in WINDOWS:
        trend = getattr(summary, f'window_{w}d_trend')
        change = getattr(summary, f'window_{w}d_change_pct')
        if len(costs) < 2 * w:
            assert trend is None
        else:
            assert trend in ('up', 'down', 'flat')
        if change is not None and trend is not None:
            if change > TREND_FLAT_BAND_PCT:
                assert trend == 'up'
            elif change < -TREND_FLAT_BAND_PCT:
                assert trend == 'down'
            else:
                assert trend == 'flat'


# ---------------------------------------------------------------------------
# Serialisation round trips
# ---------------------------------------------------------------------------


def test_ledger_row_round_trips_through_one_ndjson_line():
    row = LedgerRow(
        date=DAY, estimated=True, application_id='0192-app',
        cost=[ServiceCost(service=NOVA_ACT_SERVICE, cost=1.42, list_cost=1.5, usage_seconds=1076),
              ServiceCost(service=COMPUTE_SERVICE, cost=0.11, list_cost=0.12, usage_seconds=1310, launches=3)],
        buckets=Buckets(unassigned=0.0, unallocated=0.07, unmetered=0.0),
        collected_at=COLLECTED_AT,
    )
    line = row.model_dump_json()
    assert '\n' not in line
    parsed = json.loads(line)
    assert parsed['date'] == '2026-11-04'
    assert parsed['cost'][1]['launches'] == 3
    assert parsed['buckets'] == {'unassigned': 0.0, 'unallocated': 0.07, 'unmetered': 0.0}
    assert LedgerRow.model_validate_json(line) == row


def test_ledger_row_money_is_rounded_to_six_decimals_on_output_only():
    row = _row(DAY, cost=1.23456789, list_cost=2.0000004)
    assert row.cost[0].cost == 1.23456789          # in-memory value untouched (never round before summing)
    dumped = json.loads(row.model_dump_json())
    assert dumped['cost'][0]['cost'] == 1.234568
    assert dumped['cost'][0]['list_cost'] == 2.0
    assert row.model_dump()['cost'][0]['cost'] == 1.234568


def test_ledger_row_totals():
    row = _row(DAY, cost=1.0, list_cost=2.0, compute=0.5)
    assert row.total() == pytest.approx(1.5)
    assert row.total_list() == pytest.approx(2.5)


def _summary() -> CostSummary:
    return CostSummary(
        as_of=DAY,
        window_1d=1.42, window_1d_trend='up', window_1d_change_pct=29.1, window_1d_list=1.5,
        window_7d=9.8, window_7d_trend='up', window_7d_change_pct=10.1, window_7d_list=10.2,
        window_30d=42.1, window_30d_trend=None, window_30d_change_pct=None, window_30d_list=44.0,
        by_source_30d={NOVA_ACT_SERVICE: 39.0, COMPUTE_SERVICE: 3.1},
        days_available=31, estimated_days=1, updated_at=UPDATED_AT,
    )


def test_cost_summary_to_item_is_a_resource_item_with_decimals():
    item = _summary().to_item(application_dimension_key('app-a'))
    assert item['pk'] == 'USAGE#APPLICATION#app-a'
    assert item['sk'] == SUMMARY_SK
    assert item['as_of'] == '2026-11-04'
    assert item['window_1d'] == Decimal('1.42')
    assert item['window_30d_trend'] is None
    assert item['by_source_30d'] == {NOVA_ACT_SERVICE: Decimal('39.0'), COMPUTE_SERVICE: Decimal('3.1')}
    assert item['days_available'] == 31
    assert not any(isinstance(v, float) for v in item.values())


def test_cost_summary_round_trips_through_resource_item():
    summary = _summary()
    item = summary.to_item(OVERALL_DIMENSION_KEY)
    assert CostSummary.from_item(item) == summary
    # resource-API reads hand back Decimals for every number
    assert CostSummary.from_item({**item, 'days_available': Decimal('31')}) == summary


def test_cost_summary_round_trips_through_dynamodb_typed_item():
    summary = _summary()
    typed = summary.to_typed_item(usecase_dimension_key('u-1'))
    assert typed['pk'] == {'S': 'USAGE#USECASE#u-1'}
    assert typed['sk'] == {'S': SUMMARY_SK}
    assert typed['window_1d'] == {'N': '1.42'}
    assert typed['window_30d_trend'] == {'NULL': True}
    assert typed['by_source_30d'] == {'M': {NOVA_ACT_SERVICE: {'N': '39.0'}, COMPUTE_SERVICE: {'N': '3.1'}}}
    # the same shape the low-level client produces
    assert typed == TypeSerializer().serialize(summary.to_item(usecase_dimension_key('u-1')))['M']
    assert CostSummary.from_typed_item(typed) == summary
    plain = {k: TypeDeserializer().deserialize(v) for k, v in typed.items()}
    assert CostSummary.from_item(plain) == summary


def test_cost_summary_api_shape_is_snake_case_json():
    body = _summary().model_dump(mode='json')
    assert body['as_of'] == '2026-11-04'
    assert body['window_30d_trend'] is None
    assert 'pk' not in body


def test_summarize_output_round_trips_through_item():
    rows = _daily_rows(DAY, 20, lambda i: 0.1 * i)
    summary = summarize(rows, DAY, updated_at=UPDATED_AT)
    restored = CostSummary.from_item(summary.to_item(OVERALL_DIMENSION_KEY))
    assert restored.model_dump() == summary.model_dump()


def test_collector_run_report_defaults_and_log_record():
    report = CollectorRunReport(days=[DAY], billed_usd=10.0, allocated_usd=9.5, unallocated_usd=0.3,
                               unmetered_usd=0.2, definitions=4, pages=2, files_written=7, duration_s=12.345)
    assert report.skipped_days == []
    assert report.continued_with == []
    record = report.as_log_record()
    assert record['event'] == 'cost_collector.run'
    assert record['days'] == ['2026-11-04']
    assert record['billed_usd'] == 10.0
    assert record['skipped_days'] == []
    json.dumps(record)   # loggable as one structured line
    report = CollectorRunReport(days=[], skipped_days=[SkippedDay(day=DAY, reason='deadline')],
                               continued_with=[DAY])
    assert report.as_log_record()['skipped_days'] == [{'day': '2026-11-04', 'reason': 'deadline'}]
    assert report.as_log_record()['continued_with'] == ['2026-11-04']
    assert report.billed_usd == 0.0
    assert report.compute_wallclock_fallbacks == 0 and report.compute_running_executions == 0
    record = CollectorRunReport(compute_wallclock_fallbacks=3, compute_running_executions=1).as_log_record()
    assert record['compute_wallclock_fallbacks'] == 3 and record['compute_running_executions'] == 1


def test_module_has_no_boto3_client_at_import():
    """The module is pure: it must not create AWS clients or read the environment."""
    assert not hasattr(cost_models, 'boto3')
    assert not hasattr(cost_models, 'os')
