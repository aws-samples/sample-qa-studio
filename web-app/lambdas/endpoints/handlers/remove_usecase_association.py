import logging
from typing import Any, Dict
import boto3
from utils import create_response, get_table_name, require_scopes, validate_path_id

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    user_identity, error_response = require_scopes(event, ['api/applications.write'])
    if error_response:
        return error_response

    path_params = event.get('pathParameters', {})
    app_id, error = validate_path_id(path_params.get('id'), 'application ID')
    if error:
        return error
    usecase_id, error = validate_path_id(path_params.get('usecaseId'), 'usecase ID')
    if error:
        return error

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(get_table_name())

    table.delete_item(Key={'pk': f'APPLICATION#{app_id}', 'sk': f'USECASE#{usecase_id}'})

    # Clear application_id from the usecase
    try:
        table.update_item(
            Key={'pk': 'USECASES', 'sk': f'USECASE#{usecase_id}'},
            UpdateExpression='REMOVE application_id',
            ConditionExpression='attribute_exists(pk)',
        )
    except Exception:
        logger.warning(f"Could not clear application_id from usecase {usecase_id}")

    # Decrement usecase_count
    table.update_item(
        Key={'pk': f'APPLICATION#{app_id}', 'sk': 'METADATA'},
        UpdateExpression='ADD usecase_count :dec',
        ExpressionAttributeValues={':dec': -1},
    )

    logger.info(f"Removed usecase {usecase_id} from application {app_id}")
    return create_response(200, {'status': 'association removed'})
