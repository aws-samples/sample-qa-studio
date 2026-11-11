import logging
from typing import Any, Dict
import boto3
from utils import get_table_name, create_response
from resource_auth import require_resource_access, usecase_from_path
from permissions_repo import get_usecase_owner
from variable_merge import load_effective_usecase_variables, table_item_reader

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('view', usecase_from_path, scopes=['api/usecases.read'], allow_worker=True)
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to get the *effective* variables of a use case.

    Application-level rows (``APPLICATION#{app} / VARIABLES``) come first,
    sorted by key and tagged ``source: "application"``; the use case's own
    rows (``USECASE_VARIABLES``) follow in stored order, tagged
    ``source: "usecase"``, and shadow application keys. The editor renders
    inherited rows read-only and saves only its own; the CLI, TUI and worker
    read ``key`` / ``value`` only.

    Args:
        event: API Gateway proxy request event
        context: Lambda context

    Returns:
        API Gateway proxy response ``{variables: [{key, value, source}]}``
    """
    try:
        # Get use case ID from path parameters
        usecase_id = event['pathParameters']['id']  # validated by the resolver

        # The owner lookup the decorator already made (USECASES / USECASE#{id})
        # carries the application id; one projected get_item, no query.
        owner = get_usecase_owner(usecase_id) or {}
        application_id = owner.get('application_id')

        # Initialize Amazon DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())

        variables = load_effective_usecase_variables(table_item_reader(table), usecase_id, application_id)
        return create_response(200, {'variables': variables})

    except Exception as e:
        logger.error(f"Error getting use case variables: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
