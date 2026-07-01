import logging
from typing import Any, Dict
import boto3
from boto3.dynamodb.conditions import Key
from utils import create_response, get_table_name, require_scopes, validate_path_id

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    user_identity, error_response = require_scopes(event, ['api/applications.write'])
    if error_response:
        return error_response

    app_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'application ID')
    if error:
        return error

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(get_table_name())

    # Query all association records under this application
    assoc_response = table.query(
        KeyConditionExpression=Key('pk').eq(f'APPLICATION#{app_id}') & Key('sk').begins_with('USECASE#')
    )

    # Clear application_id from associated usecases and delete association records
    with table.batch_writer() as batch:
        for item in assoc_response.get('Items', []):
            usecase_id = item['sk'].replace('USECASE#', '')
            # Remove association record
            batch.delete_item(Key={'pk': f'APPLICATION#{app_id}', 'sk': item['sk']})
            # Clear application_id on the usecase
            try:
                table.update_item(
                    Key={'pk': 'USECASES', 'sk': f'USECASE#{usecase_id}'},
                    UpdateExpression='REMOVE application_id',
                    ConditionExpression='attribute_exists(pk)',
                )
            except Exception:
                logger.warning(f"Could not clear application_id from usecase {usecase_id}")

    # Delete METADATA record
    table.delete_item(Key={'pk': f'APPLICATION#{app_id}', 'sk': 'METADATA'})

    # Delete index record
    table.delete_item(Key={'pk': 'APPLICATIONS', 'sk': f'APPLICATION#{app_id}'})

    logger.info(f"Deleted application {app_id}")
    return create_response(200, {'status': 'application deleted', 'id': app_id})
