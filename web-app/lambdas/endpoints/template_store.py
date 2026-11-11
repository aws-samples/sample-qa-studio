"""Template metadata access and version tracking.

Template metadata lives at ``pk=TEMPLATES, sk=TEMPLATE#{id}`` and its steps
at ``pk=TEMPLATE#{id}, sk=STEP#{uuid}``.  ``version`` is template-level:
every change to the template — metadata *or* any step create / update /
delete / reorder — increments it, and usecase steps that were inserted from
the template carry the ``template_version`` they were copied at.
``check_template_updates`` compares the two.

Per-step versioning is deliberately out of scope (v1).
"""
import logging
from typing import Any, Dict, Optional

from botocore.exceptions import ClientError

from utils import get_current_timestamp

logger = logging.getLogger()

TEMPLATES_PK = 'TEMPLATES'

#: Shared by the resource-API bump and the low-level transact item.
_BUMP_UPDATE_EXPRESSION = 'SET updated_at = :updated_at ADD #version :one'
_BUMP_ATTRIBUTE_NAMES = {'#version': 'version'}
#: Never upsert: a bump on a missing template must not create a record.
_BUMP_CONDITION = 'attribute_exists(pk)'


def template_sk(template_id: str) -> str:
    return f'TEMPLATE#{template_id}'


def get_template_metadata(table, template_id: str) -> Optional[Dict[str, Any]]:
    """Return the template metadata item, or ``None`` when it does not exist."""
    response = table.get_item(Key={'pk': TEMPLATES_PK, 'sk': template_sk(template_id)})
    return response.get('Item')


def bump_template_version(table, template_id: str) -> Optional[int]:
    """Increment the template's ``version`` after a successful step write.

    Returns the new version, or ``None`` (logged) when the template metadata
    record does not exist — the step write itself has already succeeded, so
    the caller keeps its success response.
    """
    try:
        response = table.update_item(
            Key={'pk': TEMPLATES_PK, 'sk': template_sk(template_id)},
            UpdateExpression=_BUMP_UPDATE_EXPRESSION,
            ConditionExpression=_BUMP_CONDITION,
            ExpressionAttributeNames=_BUMP_ATTRIBUTE_NAMES,
            ExpressionAttributeValues={':updated_at': get_current_timestamp(), ':one': 1},
            ReturnValues='UPDATED_NEW',
        )
    except ClientError as e:
        if e.response.get('Error', {}).get('Code') == 'ConditionalCheckFailedException':
            logger.warning(f"bump_template_version: template {template_id} has no metadata record; version not bumped")
            return None
        raise
    return int(response.get('Attributes', {}).get('version', 0))


def bump_template_version_transact_item(table_name: str, template_id: str) -> Dict[str, Any]:
    """The same bump as a ``transact_write_items`` entry (low-level typed format).

    Used by callers that already write their step changes in one transaction
    (``reorder_template_steps``) so the version moves atomically with them.
    """
    return {
        'Update': {
            'TableName': table_name,
            'Key': {'pk': {'S': TEMPLATES_PK}, 'sk': {'S': template_sk(template_id)}},
            'UpdateExpression': _BUMP_UPDATE_EXPRESSION,
            'ConditionExpression': _BUMP_CONDITION,
            'ExpressionAttributeNames': _BUMP_ATTRIBUTE_NAMES,
            'ExpressionAttributeValues': {
                ':updated_at': {'S': get_current_timestamp()},
                ':one': {'N': '1'},
            },
        }
    }
