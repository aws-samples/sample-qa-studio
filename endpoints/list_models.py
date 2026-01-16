import logging
from typing import Any, Dict, List
import boto3
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
    try:
        # Create Nova Act client in us-east-1 (GA region)
        novaact_client = boto3.client('nova-act', region_name=NOVA_ACT_REGION)
        
        # List all available models
        response = novaact_client.list_models(
            ClientCompatibilityVersion=1
        )
        
        # Convert to response format
        models = []
        for model in response.get('ModelSummaries', []):
            model_id = model.get('ModelId', '')
            
            # Determine lifecycle status
            lifecycle_status = 'available'
            if 'ModelLifecycle' in model and model['ModelLifecycle'].get('Status'):
                lifecycle_status = model['ModelLifecycle']['Status']
            
            models.append({
                'modelId': model_id,
                'modelName': model_id,  # Use modelId as name
                'isDefault': model_id == DEFAULT_MODEL,
                'description': f'Status: {lifecycle_status}'
            })
        
        # If no models found or default not in list, add default model
        has_default = any(m['modelId'] == DEFAULT_MODEL for m in models)
        
        if not has_default:
            models.insert(0, {
                'modelId': DEFAULT_MODEL,
                'modelName': DEFAULT_MODEL,
                'isDefault': True,
                'description': 'Default Nova Act model'
            })
        
        return create_response(200, {
            'models': models,
            'defaultModel': DEFAULT_MODEL
        })
        
    except Exception as e:
        logger.error(f"Error listing models: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
