import logging
import re
from typing import Any, Dict
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from utils import create_response, get_table_name, require_scopes, validate_path_id

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to delete a usecase and all related data.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with deletion confirmation
    """
    try:
        # Validate scope (requires usecases.write or admin)
        user_identity, error_response = require_scopes(event, ['api/usecases.write'])
        if error_response:
            return error_response
        
        # Get usecase ID from path
        path_params = event.get('pathParameters', {})
        usecase_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'usecase ID')
        if error:
            return error
        
        # Initialize Amazon DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Delete Amazon Nova Act workflow definition if it exists
        delete_workflow_definition(usecase_id)
        
        # Delete usecase metadata
        table.delete_item(
            Key={
                'pk': 'USECASES',
                'sk': f'USECASE#{usecase_id}'
            }
        )
        
        # Delete CREATED_BY record (if it exists)
        try:
            table.delete_item(
                Key={
                    'pk': f'USECASE#{usecase_id}',
                    'sk': 'CREATED_BY'
                }
            )
        except Exception as e:
            logger.warning(f"Error deleting created_by record (may not exist for older usecases): {str(e)}")
        
        # Query and delete all steps
        steps_response = table.query(
            KeyConditionExpression=Key('pk').eq(f'USECASE#{usecase_id}') & Key('sk').begins_with('STEP#')
        )
        
        for item in steps_response.get('Items', []):
            table.delete_item(
                Key={
                    'pk': item['pk'],
                    'sk': item['sk']
                }
            )
        
        # Query and delete all executions
        executions_response = table.query(
            KeyConditionExpression=Key('pk').eq(f'USECASE_EXECUTION#{usecase_id}') & Key('sk').begins_with('EXECUTION#')
        )
        
        for item in executions_response.get('Items', []):
            execution_pk = item['pk']
            
            # Delete execution
            table.delete_item(
                Key={
                    'pk': execution_pk,
                    'sk': item['sk']
                }
            )
            
            # Query and delete execution steps
            execution_steps_response = table.query(
                KeyConditionExpression=Key('pk').eq(f'EXECUTION#{execution_pk}') & Key('sk').begins_with('EXECUTION_STEP#')
            )
            
            for step_item in execution_steps_response.get('Items', []):
                table.delete_item(
                    Key={
                        'pk': step_item['pk'],
                        'sk': step_item['sk']
                    }
                )
        
        logger.info(f"Successfully deleted usecase {usecase_id}")
        
        return create_response(200, {
            'status': 'usecase deleted',
            'usecaseId': usecase_id
        })
        
    except Exception as e:
        logger.error(f"Error deleting usecase: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})


def delete_workflow_definition(usecase_id: str):
    """
    Delete Nova Act workflow definition for the usecase.
    
    Args:
        usecase_id: Usecase ID
    """
    try:
        # Sanitize workflow name to match Python logic
        # Workflow names: 1-40 chars, a-z A-Z 0-9 - _, no spaces
        workflow_name = re.sub(r'[^a-zA-Z0-9\-_]', '-', usecase_id)
        
        # Limit to max 40 chars
        if len(workflow_name) > 40:
            workflow_name = workflow_name[:40]
        
        # Create Amazon Nova Act client in us-east-1 (GA region)
        novaact_client = boto3.client('nova-act', region_name='us-east-1')
        
        # Try to delete the workflow definition
        novaact_client.delete_workflow_definition(WorkflowDefinitionName=workflow_name)
        
        logger.info(f"Successfully deleted workflow definition '{workflow_name}' for usecase {usecase_id}")
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == 'ResourceNotFoundException':
            logger.info(f"Workflow definition '{workflow_name}' does not exist, nothing to delete")
        else:
            logger.warning(f"Could not delete workflow definition '{workflow_name}': {str(e)}")
    except Exception as e:
        logger.warning(f"Warning: Could not delete workflow definition: {str(e)}")
