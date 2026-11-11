"""Template usage records — which use cases have steps linked to a template.

Use-case steps inserted from a template carry ``template_id`` /
``template_step_id`` / ``template_version`` (``LINKAGE_FIELDS``), but no
index covers ``template_id``.  The reverse pointer lives in the template's
own partition::

    pk = TEMPLATE#{template_id}
    sk = USAGE#{usecase_id}
    template_id, usecase_id, created_at

One record per (template, use case) — no step count, counts drift and are
computed on read.  Writes are idempotent ``put_item``s.  Because the record
sits under ``TEMPLATE#{id}``, the partition wipe in ``delete_template``
removes it together with the steps and variables.

Every handler that creates or destroys linkage goes through here:
``import_template`` / ``import_usecase`` record, ``delete_usecase`` /
``delete_step`` remove, ``delete_template`` unlinks the use-case steps
*before* deleting the template, ``get_template_usages`` lists.
"""
import logging
from typing import Any, Dict, List

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from utils import get_current_timestamp

logger = logging.getLogger()

#: Attributes a use-case step carries when it was inserted from a template
#: (written by ``template_expansion.build_linked_steps``).
LINKAGE_FIELDS = ('template_id', 'template_step_id', 'template_version')

USAGE_SK_PREFIX = 'USAGE#'

_UNLINK_UPDATE_EXPRESSION = 'REMOVE ' + ', '.join(LINKAGE_FIELDS)
#: Never strip a step that was relinked (to another template) concurrently.
_UNLINK_CONDITION = 'template_id = :tid'


def template_pk(template_id: str) -> str:
    return f'TEMPLATE#{template_id}'


def usage_sk(usecase_id: str) -> str:
    return f'{USAGE_SK_PREFIX}{usecase_id}'


def usage_item(template_id: str, usecase_id: str, now: str) -> Dict[str, Any]:
    """The USAGE record for ``(template_id, usecase_id)``, first linked at ``now``."""
    return {
        'pk': template_pk(template_id),
        'sk': usage_sk(usecase_id),
        'template_id': template_id,
        'usecase_id': usecase_id,
        'created_at': now,
    }


def record_usage(table, template_id: str, usecase_id: str) -> None:
    """Idempotent: inserting the same template into a use case twice is a no-op."""
    table.put_item(Item=usage_item(template_id, usecase_id, get_current_timestamp()))


def list_usages(table, template_id: str) -> List[Dict[str, Any]]:
    """Every USAGE record of the template (paginated query)."""
    usages: List[Dict[str, Any]] = []
    kwargs: Dict[str, Any] = {
        'KeyConditionExpression': Key('pk').eq(template_pk(template_id)) & Key('sk').begins_with(USAGE_SK_PREFIX),
    }
    while True:
        response = table.query(**kwargs)
        usages.extend(response.get('Items', []))
        last_key = response.get('LastEvaluatedKey')
        if not last_key:
            return usages
        kwargs['ExclusiveStartKey'] = last_key


def remove_usage(table, template_id: str, usecase_id: str) -> None:
    """Delete the USAGE record; absent records are fine (DynamoDB delete is idempotent)."""
    table.delete_item(Key={'pk': template_pk(template_id), 'sk': usage_sk(usecase_id)})


def _usecase_steps(table, usecase_id: str) -> List[Dict[str, Any]]:
    return table.query(
        KeyConditionExpression=Key('pk').eq(f'USECASE#{usecase_id}') & Key('sk').begins_with('STEP#')
    ).get('Items', [])


def remove_usage_if_unlinked(table, template_id: str, usecase_id: str) -> bool:
    """Drop the USAGE record when no step of the use case still links to the template.

    Returns ``True`` when the record was removed.
    """
    if any(step.get('template_id') == template_id for step in _usecase_steps(table, usecase_id)):
        return False
    remove_usage(table, template_id, usecase_id)
    return True


def unlink_usecase_steps(table, template_id: str, usecase_id: str) -> int:
    """Turn the use case's steps linked to ``template_id`` into plain steps.

    Removes ``LINKAGE_FIELDS`` from every step whose ``template_id`` matches;
    the step definition itself is untouched.  The update is conditional on
    ``template_id`` still being the one we read, so a step relinked
    concurrently is skipped (``ConditionalCheckFailedException`` swallowed).
    Returns the number of steps unlinked.
    """
    unlinked = 0
    for step in _usecase_steps(table, usecase_id):
        if step.get('template_id') != template_id:
            continue
        try:
            table.update_item(
                Key={'pk': step['pk'], 'sk': step['sk']},
                UpdateExpression=_UNLINK_UPDATE_EXPRESSION,
                ConditionExpression=_UNLINK_CONDITION,
                ExpressionAttributeValues={':tid': template_id},
            )
        except ClientError as e:
            if e.response.get('Error', {}).get('Code') == 'ConditionalCheckFailedException':
                logger.info(f"unlink_usecase_steps: step {step.get('id')} of {usecase_id} was relinked; skipped")
                continue
            raise
        unlinked += 1
    return unlinked
