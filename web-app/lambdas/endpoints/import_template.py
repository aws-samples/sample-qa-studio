import logging
import json
from typing import Any, Dict, List
from uuid import uuid4
import boto3
from boto3.dynamodb.conditions import Key
from utils import create_response, get_table_name, get_current_timestamp, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to import template steps into a usecase.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with import confirmation
    """
    try:
        # Validate scope authorization
        user_identity, error = require_scopes(event, ['api/usecases.write'])
        if error:
            return error
        
        # Get usecase ID from path
        path_params = event.get('pathParameters', {})
        usecase_id = path_params.get('id')
        
        if not usecase_id:
            return create_response(400, {'error': 'Missing usecase ID'})
        
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return create_response(400, {'error': 'Invalid JSON in request body'})
        
        template_id = body.get('template_id', '')
        insert_position = body.get('insert_position', -1)
        
        if not template_id:
            return create_response(400, {'error': 'template_id is required'})
        
        # Initialize DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # 1. Get template metadata to get current version
        template_response = table.get_item(
            Key={
                'pk': 'TEMPLATES',
                'sk': f'TEMPLATE#{template_id}'
            }
        )
        
        if 'Item' not in template_response:
            return create_response(404, {'error': 'Template not found'})
        
        template = template_response['Item']
        
        # 2. Get template steps
        template_steps_response = table.query(
            KeyConditionExpression=Key('pk').eq(f'TEMPLATE#{template_id}') & Key('sk').begins_with('STEP#')
        )
        
        template_steps = template_steps_response.get('Items', [])
        
        logger.info(f"Template has {len(template_steps)} steps (before sorting)")
        for i, step in enumerate(template_steps):
            logger.info(f"BEFORE SORT - Template step {i}: sort={step.get('sort')}, instruction={step.get('instruction')}")
        
        # Sort template steps by sort order
        template_steps.sort(key=lambda x: x.get('sort', 0))
        
        logger.info(f"Template has {len(template_steps)} steps (after sorting)")
        for i, step in enumerate(template_steps):
            logger.info(f"AFTER SORT - Template step {i}: sort={step.get('sort')}, instruction={step.get('instruction')}")
        
        # 3. Get existing use case steps to determine insertion point
        existing_steps_response = table.query(
            KeyConditionExpression=Key('pk').eq(f'USECASE#{usecase_id}') & Key('sk').begins_with('STEP#')
        )
        
        existing_steps = existing_steps_response.get('Items', [])
        
        # Sort existing steps
        existing_steps.sort(key=lambda x: x.get('sort', 0))
        
        # 4. Calculate new sort orders
        if insert_position == -1:
            # Insert at end
            if existing_steps:
                insert_position = existing_steps[-1].get('sort', 0) + 1
            else:
                insert_position = 1  # Use 1-based indexing to match use case convention
        elif insert_position == 0:
            # Insert at beginning - use 1-based indexing
            insert_position = 1
        
        # 5. Create new steps from template
        new_steps = []
        now = get_current_timestamp()
        
        logger.info(f"Insert position: {insert_position}")
        
        for i, template_step in enumerate(template_steps):
            new_step_id = str(uuid4())
            new_sort_order = insert_position + i
            
            logger.info(f"Creating step {i} with sort order {new_sort_order} from template step with sort {template_step.get('sort')}")
            
            new_step = {
                'pk': f'USECASE#{usecase_id}',
                'sk': f'STEP#{new_step_id}',
                'id': new_step_id,
                'sort': new_sort_order,
                'instruction': template_step.get('instruction', ''),
                'step_type': template_step.get('step_type', ''),
                'created_at': now,
                # Template reference fields
                'template_id': template_id,
                'template_step_id': template_step.get('id', ''),
                'template_version': template.get('version', 1)
            }
            
            # Add optional fields if present
            if template_step.get('secret_key'):
                new_step['secret_key'] = template_step['secret_key']
            if template_step.get('capture_variable'):
                new_step['capture_variable'] = template_step['capture_variable']
            if template_step.get('validation_type'):
                new_step['validation_type'] = template_step['validation_type']
            if template_step.get('validation_operator'):
                new_step['validation_operator'] = template_step['validation_operator']
            if template_step.get('validation_value'):
                new_step['validation_value'] = template_step['validation_value']
            if template_step.get('assertion_variable'):
                new_step['assertion_variable'] = template_step['assertion_variable']
            if template_step.get('value_type'):
                new_step['value_type'] = template_step['value_type']
            
            new_steps.append(new_step)
        
        # 6. Update sort orders for steps after insertion point
        updated_steps = []
        for step in existing_steps:
            if step.get('sort', 0) >= insert_position:
                step['sort'] = step['sort'] + len(template_steps)
                updated_steps.append(step)
        
        # 7. Write all changes to DynamoDB SEQUENTIALLY to avoid race conditions
        logger.info(f"Writing {len(new_steps)} new steps to DynamoDB SEQUENTIALLY")
        
        # Write new steps ONE AT A TIME in order
        for i, step in enumerate(new_steps):
            logger.info(f"Writing new step {i}: sort={step['sort']}, instruction={step['instruction']}")
            table.put_item(Item=step)
            logger.info(f"Successfully wrote step {i} with sort={step['sort']}")
        
        # Update existing steps ONE AT A TIME
        logger.info(f"Updating {len(updated_steps)} existing steps")
        for i, step in enumerate(updated_steps):
            logger.info(f"Updating existing step {i}: sort={step['sort']}")
            table.put_item(Item=step)
        
        logger.info(f"Successfully wrote all {len(new_steps)} steps sequentially")
        
        # 8. Get template variables and merge with use case variables
        try:
            template_vars_response = table.get_item(
                Key={
                    'pk': f'TEMPLATE#{template_id}',
                    'sk': 'VARIABLES'
                }
            )
            
            if 'Item' in template_vars_response:
                template_vars = template_vars_response['Item'].get('variables', [])
                
                if template_vars:
                    # Get existing use case variables
                    usecase_vars_response = table.get_item(
                        Key={
                            'pk': f'USECASE#{usecase_id}',
                            'sk': 'USECASE_VARIABLES'
                        }
                    )
                    
                    if 'Item' in usecase_vars_response:
                        usecase_vars = usecase_vars_response['Item']
                    else:
                        usecase_vars = {
                            'pk': f'USECASE#{usecase_id}',
                            'sk': 'USECASE_VARIABLES',
                            'variables': [],
                            'created_at': now
                        }
                    
                    # Merge variables (don't overwrite existing ones)
                    existing_keys = {v.get('key') for v in usecase_vars.get('variables', [])}
                    
                    for template_var in template_vars:
                        if template_var.get('key') not in existing_keys:
                            usecase_vars.setdefault('variables', []).append(template_var)
                    
                    # Save merged variables
                    table.put_item(Item=usecase_vars)
        except Exception as e:
            logger.warning(f"Error merging template variables: {str(e)}")
        
        return create_response(201, {
            'message': 'Template imported successfully',
            'steps_created': len(new_steps)
        })
        
    except Exception as e:
        logger.error(f"Error importing template: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
