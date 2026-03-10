import lambda_init  # Must be first to set up Python path
import logging
from typing import Any, Dict, List
import boto3
import botocore
from botocore.exceptions import ClientError
from utils import create_response

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_MODEL = "nova-act-v1.0"
NOVA_ACT_REGION = "us-east-1"


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to list available Nova Act models.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with list of models
    """
    print(boto3.__version__)
    try:
        # Create Amazon Nova Act client in us-east-1 (GA region)
        novaact_client = boto3.client('nova-act', region_name=NOVA_ACT_REGION)
        
        # List all available models
        response = novaact_client.list_models(
            clientCompatibilityVersion=1
        )
        
        # Convert to response format
        models = []
        for model in response.get('modelSummaries', []):
            model_id = model.get('modelId', '')
            
            # Determine lifecycle status
            lifecycle_status = 'available'
            if 'modelLifecycle' in model and model['modelLifecycle'].get('status'):
                lifecycle_status = model['modelLifecycle']['status'].lower()
            
            models.append({
                'modelId': model_id,
                'modelName': model_id,  # Use modelId as name
                'isDefault': model_id == DEFAULT_MODEL,
                'description': f'Status: {lifecycle_status}',
                'status': lifecycle_status
            })
        
        # Add model aliases if available
        for alias in response.get('modelAliases', []):
            alias_name = alias.get('aliasName', '')
            resolved_model_id = alias.get('resolvedModelId', '')
            
            if alias_name:
                models.append({
                    'modelId': alias_name,
                    'modelName': alias_name,
                    'isDefault': alias_name == DEFAULT_MODEL,
                    'description': f'Alias for {resolved_model_id}',
                    'status': 'alias'
                })
        
        # If no models found or default not in list, add default model
        has_default = any(m['modelId'] == DEFAULT_MODEL for m in models)
        
        if not has_default:
            models.insert(0, {
                'modelId': DEFAULT_MODEL,
                'modelName': DEFAULT_MODEL,
                'isDefault': True,
                'description': 'Default Nova Act model',
                'status': 'available'
            })
        
        return create_response(200, {
            'models': models,
            'defaultModel': DEFAULT_MODEL
        })
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        logger.error(f"AWS ClientError listing models: {error_code} - {str(e)}", exc_info=True)
        return create_response(500, {'error': f'AWS API error: {error_code}'})
    except Exception as e:
        logger.error(f"Error listing models: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
