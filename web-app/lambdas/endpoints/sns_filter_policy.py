"""Per-user use-case notification filter on the SNS topic.

Each subscriber has one email subscription whose ``FilterPolicy`` is
``{"usecase_id": [...]}``; the policy on the subscription is the only source of
truth for which use cases notify that user.  Used by ``subscribe_usecase`` and
``unsubscribe_usecase``.
"""
import json
import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

PENDING_CONFIRMATION = 'PendingConfirmation'


def filter_policy_json(usecase_ids: List[str]) -> str:
    """The FilterPolicy attribute value for ``usecase_ids``."""
    return json.dumps({'usecase_id': usecase_ids})


def find_email_subscription(sns_client: Any, topic_arn: str, email: str, confirmed_only: bool) -> Optional[str]:
    """SubscriptionArn of ``email``'s email subscription on the topic, or ``None``.

    With ``confirmed_only`` a pending subscription counts as none; otherwise its
    ARN is the literal ``PendingConfirmation``.
    """
    response = sns_client.list_subscriptions_by_topic(TopicArn=topic_arn)
    for subscription in response.get('Subscriptions', []):
        arn = subscription.get('SubscriptionArn')
        if subscription.get('Endpoint') != email or subscription.get('Protocol') != 'email':
            continue
        if confirmed_only and arn == PENDING_CONFIRMATION:
            continue
        return arn
    return None


def read_usecase_filter(sns_client: Any, subscription_arn: str) -> List[str]:
    """The ``usecase_id`` list of the subscription's FilterPolicy (``[]`` when unset).

    Raises when the attributes cannot be read or the policy is not JSON.
    """
    response = sns_client.get_subscription_attributes(SubscriptionArn=subscription_arn)
    policy = response.get('Attributes', {}).get('FilterPolicy')
    if not policy:
        return []
    return json.loads(policy).get('usecase_id', [])


def write_usecase_filter(sns_client: Any, subscription_arn: str, usecase_ids: List[str]) -> None:
    sns_client.set_subscription_attributes(
        SubscriptionArn=subscription_arn,
        AttributeName='FilterPolicy',
        AttributeValue=filter_policy_json(usecase_ids),
    )


def add_usecase(sns_client: Any, subscription_arn: str, usecase_id: str) -> None:
    """Add ``usecase_id`` to the filter. An unreadable policy starts fresh."""
    try:
        current = read_usecase_filter(sns_client, subscription_arn)
    except Exception as e:
        logger.warning(f"Could not get current filter policy, starting fresh: {str(e)}")
        current = []
    if usecase_id not in current:
        current.append(usecase_id)
    write_usecase_filter(sns_client, subscription_arn, current)
    logger.info(f"Filter policy now covers {len(current)} use case(s)")


def remove_usecase(sns_client: Any, subscription_arn: str, usecase_id: str) -> None:
    """Remove ``usecase_id``; with nothing left the subscription is deleted.

    A use case that is not in the filter is a no-op. Read errors propagate.
    """
    current = read_usecase_filter(sns_client, subscription_arn)
    if usecase_id not in current:
        logger.warning(f"Use case {usecase_id} not in the subscription's filter policy - nothing to remove")
        return
    remaining = [uid for uid in current if uid != usecase_id]
    if not remaining:
        sns_client.unsubscribe(SubscriptionArn=subscription_arn)
        logger.info("No use cases left in the filter policy; unsubscribed")
        return
    write_usecase_filter(sns_client, subscription_arn, remaining)
    logger.info(f"Filter policy now covers {len(remaining)} use case(s)")
