"""step_reorder.py and sns_filter_policy.py (shared by the reorder and
subscribe/unsubscribe Lambdas)."""
import json
from unittest.mock import MagicMock

import pytest

from step_reorder import parse_step_orders, sort_update_items
from sns_filter_policy import (
    PENDING_CONFIRMATION,
    add_usecase,
    filter_policy_json,
    find_email_subscription,
    read_usecase_filter,
    remove_usecase,
)


# ── step_reorder ─────────────────────────────────────────────────────────


class TestParseStepOrders:
    def test_returns_orders(self):
        orders, error = parse_step_orders({'body': json.dumps({'step_orders': [{'step_id': 'a', 'sort': 1}]})})
        assert error is None
        assert orders == [{'step_id': 'a', 'sort': 1}]

    @pytest.mark.parametrize('body,message', [
        ('not json', 'Invalid request body'),
        (json.dumps({}), 'step_orders is required'),
        (json.dumps({'step_orders': []}), 'step_orders is required'),
    ])
    def test_bad_bodies_are_400(self, body, message):
        orders, error = parse_step_orders({'body': body})
        assert orders is None
        assert error['statusCode'] == 400
        assert json.loads(error['body'])['error'] == message


class TestSortUpdateItems:
    def test_one_update_per_order_with_key_layout(self):
        items = sort_update_items('t', 'TEMPLATE#x', [{'step_id': 's1', 'sort': 2}, {'step_id': 's2', 'sort': 1}],
                                  sk_for=lambda sid: f'STEP#{sid}')
        assert items == [
            {'Update': {'TableName': 't', 'Key': {'pk': {'S': 'TEMPLATE#x'}, 'sk': {'S': 'STEP#s1'}},
                        'UpdateExpression': 'SET sort = :sort',
                        'ExpressionAttributeValues': {':sort': {'N': '2'}}}},
            {'Update': {'TableName': 't', 'Key': {'pk': {'S': 'TEMPLATE#x'}, 'sk': {'S': 'STEP#s2'}},
                        'UpdateExpression': 'SET sort = :sort',
                        'ExpressionAttributeValues': {':sort': {'N': '1'}}}},
        ]

    def test_usecase_layout_uses_the_sent_sort_key(self):
        [item] = sort_update_items('t', 'USECASE#u', [{'step_id': 'STEP#s1', 'sort': 3}], sk_for=lambda sid: sid)
        assert item['Update']['Key']['sk'] == {'S': 'STEP#s1'}


# ── sns_filter_policy ────────────────────────────────────────────────────


def _sns(subscriptions=(), policy=None):
    sns = MagicMock()
    sns.list_subscriptions_by_topic.return_value = {'Subscriptions': list(subscriptions)}
    attrs = {'FilterPolicy': json.dumps(policy)} if policy is not None else {}
    sns.get_subscription_attributes.return_value = {'Attributes': attrs}
    return sns


def _sub(email, arn, protocol='email'):
    return {'Endpoint': email, 'Protocol': protocol, 'SubscriptionArn': arn}


class TestFindEmailSubscription:
    def test_matches_email_and_protocol(self):
        sns = _sns([_sub('b@x', 'arn-b'), _sub('a@x', 'arn-sms', protocol='sms'), _sub('a@x', 'arn-a')])
        assert find_email_subscription(sns, 'topic', 'a@x', confirmed_only=True) == 'arn-a'

    def test_pending_is_returned_unless_confirmed_only(self):
        sns = _sns([_sub('a@x', PENDING_CONFIRMATION)])
        assert find_email_subscription(sns, 'topic', 'a@x', confirmed_only=False) == PENDING_CONFIRMATION
        assert find_email_subscription(sns, 'topic', 'a@x', confirmed_only=True) is None

    def test_none_when_absent(self):
        assert find_email_subscription(_sns(), 'topic', 'a@x', confirmed_only=False) is None


class TestReadAndWrite:
    def test_read_missing_policy_is_empty(self):
        assert read_usecase_filter(_sns(), 'arn') == []

    def test_read_policy(self):
        assert read_usecase_filter(_sns(policy={'usecase_id': ['u1']}), 'arn') == ['u1']

    def test_filter_policy_json(self):
        assert json.loads(filter_policy_json(['u1', 'u2'])) == {'usecase_id': ['u1', 'u2']}


class TestAddUsecase:
    def test_appends_once(self):
        sns = _sns(policy={'usecase_id': ['u1']})
        add_usecase(sns, 'arn', 'u2')
        add_usecase(_sns(policy={'usecase_id': ['u1']}), 'arn', 'u1')
        sns.set_subscription_attributes.assert_called_once_with(
            SubscriptionArn='arn', AttributeName='FilterPolicy', AttributeValue=filter_policy_json(['u1', 'u2']))

    def test_unreadable_policy_starts_fresh(self):
        sns = _sns()
        sns.get_subscription_attributes.side_effect = RuntimeError('denied')
        add_usecase(sns, 'arn', 'u1')
        assert sns.set_subscription_attributes.call_args.kwargs['AttributeValue'] == filter_policy_json(['u1'])


class TestRemoveUsecase:
    def test_removes_and_keeps_the_rest(self):
        sns = _sns(policy={'usecase_id': ['u1', 'u2']})
        remove_usecase(sns, 'arn', 'u1')
        assert sns.set_subscription_attributes.call_args.kwargs['AttributeValue'] == filter_policy_json(['u2'])
        sns.unsubscribe.assert_not_called()

    def test_last_usecase_unsubscribes(self):
        sns = _sns(policy={'usecase_id': ['u1']})
        remove_usecase(sns, 'arn', 'u1')
        sns.unsubscribe.assert_called_once_with(SubscriptionArn='arn')
        sns.set_subscription_attributes.assert_not_called()

    def test_unknown_usecase_is_a_noop(self):
        sns = _sns(policy={'usecase_id': ['u1']})
        remove_usecase(sns, 'arn', 'u9')
        sns.set_subscription_attributes.assert_not_called()
        sns.unsubscribe.assert_not_called()

    def test_read_errors_propagate(self):
        sns = _sns()
        sns.get_subscription_attributes.side_effect = RuntimeError('denied')
        with pytest.raises(RuntimeError):
            remove_usecase(sns, 'arn', 'u1')
