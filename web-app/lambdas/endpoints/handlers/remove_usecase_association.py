import logging
from typing import Any, Dict
import boto3
from utils import no_content_response, get_table_name, validate_path_id
from resource_auth import require_resource_access, app_from_path

logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('edit', app_from_path, scopes=['api/applications.write'])
def handle(event: Dict[str, Any]) -> Dict[str, Any]:

    path_params = event.get('pathParameters', {})
    app_id = path_params['id']  # validated by app_from_path
    usecase_id, error = validate_path_id(path_params.get('usecaseId'), 'usecase ID')
    if error:
        return error

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(get_table_name())

    table.delete_item(Key={'pk': f'APPLICATION#{app_id}', 'sk': f'USECASE#{usecase_id}'})

    # Clear application_id from the usecase, tracking whether it was actually
    # associated so usecase_count only decrements for a real removal.
    was_associated = False
    try:
        resp = table.update_item(
            Key={'pk': 'USECASES', 'sk': f'USECASE#{usecase_id}'},
            UpdateExpression='REMOVE application_id',
            # Only detach a use case that belongs to this app; edit on this
            # app must not orphan another app's use case.
            ConditionExpression='attribute_exists(pk) AND application_id = :app_id',
            ExpressionAttributeValues={':app_id': app_id},
            ReturnValues='UPDATED_OLD',
        )
        was_associated = (resp.get('Attributes') or {}).get('application_id') is not None
    except Exception:
        logger.warning(f"Could not clear application_id from usecase {usecase_id}")

    # Decrement usecase_count only if the use case was actually associated.
    if was_associated:
        table.update_item(
            Key={'pk': f'APPLICATION#{app_id}', 'sk': 'METADATA'},
            UpdateExpression='ADD usecase_count :dec',
            ExpressionAttributeValues={':dec': -1},
        )

    logger.info(f"Removed usecase {usecase_id} from application {app_id}")
    return no_content_response()
