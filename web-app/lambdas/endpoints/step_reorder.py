"""Shared body of the two reorder Lambdas (use-case steps and template steps).

Both accept ``{"step_orders": [{"step_id": ..., "sort": n}, ...]}`` and write
every new ``sort`` in one DynamoDB transaction.  The handlers keep their auth,
key layout (``sk_for``) and, for templates, the version bump.
"""
import json
from typing import Any, Callable, Dict, List, Optional, Tuple

from utils import create_response


def parse_step_orders(event: Dict[str, Any]) -> Tuple[Optional[List[dict]], Optional[Dict[str, Any]]]:
    """``(step_orders, None)`` or ``(None, 400 response)`` for a missing/invalid body."""
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return None, create_response(400, {'error': 'Invalid request body'})
    step_orders = body.get('step_orders', [])
    if not step_orders:
        return None, create_response(400, {'error': 'step_orders is required'})
    return step_orders, None


def sort_update_items(
    table_name: str,
    pk: str,
    step_orders: List[dict],
    sk_for: Callable[[str], str],
) -> List[dict]:
    """One ``TransactItems`` Update (``SET sort = :sort``) per entry, in order."""
    return [
        {
            'Update': {
                'TableName': table_name,
                'Key': {'pk': {'S': pk}, 'sk': {'S': sk_for(order.get('step_id'))}},
                'UpdateExpression': 'SET sort = :sort',
                'ExpressionAttributeValues': {':sort': {'N': str(order.get('sort'))}},
            }
        }
        for order in step_orders
    ]
