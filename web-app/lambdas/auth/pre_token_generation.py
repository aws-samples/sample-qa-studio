"""
Pre-Token Generation Lambda Trigger

This Lambda function is triggered by Cognito during token generation to inject
scopes into JWT tokens based on user group membership.

Group-to-Scope Mapping:
- users: usecases.read, usecases.write, executions.read, executions.write, usecases.execute
- admins: all user scopes + oauth-clients.manage + admin
"""

import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Define scope mappings for each group
SCOPE_MAPPINGS = {
    'users': [
        'api/usecases.read',
        'api/usecases.write',
        'api/templates.read',
        'api/templates.write',
        'api/executions.read',
        'api/executions.write',
        'api/usecases.execute',
        'api/suite.read',
        'api/suite.write',
        'api/oauth-clients.read',
        'api/oauth-clients.write',
    ],
    'admins': [
        'api/usecases.read',
        'api/usecases.write',
        'api/templates.read',
        'api/templates.write',
        'api/executions.read',
        'api/executions.write',
        'api/usecases.execute',
        'api/suite.read',
        'api/suite.write',
        'api/oauth-clients.read',
        'api/oauth-clients.write',
        'api/admin'
    ]
}


def handler(event, context):
    """
    Pre-token generation handler that injects scopes based on user groups.
    
    Args:
        event: Cognito pre-token generation V2 event
        context: Lambda context
        
    Returns:
        Modified event with scopes in claimsToAddOrOverride
    """
    try:
        logger.info(f"=== PRE-TOKEN GENERATION V2 TRIGGERED ===")
        logger.info(f"Full event: {json.dumps(event, default=str)}")
        logger.info(f"User: {event.get('userName')}")
        logger.info(f"Trigger source: {event.get('triggerSource')}")
        
        # Extract user groups from the event
        request = event.get('request', {})
        
        # V2 format: groups are in groupConfiguration.groupsToOverride
        group_config = request.get('groupConfiguration', {})
        groups = group_config.get('groupsToOverride', [])
        
        logger.info(f"Extracted groups from groupConfiguration: {groups}")
        
        # Fallback: check userAttributes for cognito:groups
        if not groups:
            user_attributes = request.get('userAttributes', {})
            logger.info(f"User attributes: {json.dumps(user_attributes, default=str)}")
            
            # cognito:groups might be a list or comma-separated string
            cognito_groups = user_attributes.get('cognito:groups', [])
            if isinstance(cognito_groups, str):
                groups = [g.strip() for g in cognito_groups.split(',') if g.strip()]
            elif isinstance(cognito_groups, list):
                groups = cognito_groups
            
            logger.info(f"Extracted groups from userAttributes: {groups}")
        
        # If still no groups, log warning but continue
        if not groups:
            logger.warning("No groups found for user - token will have no custom scopes")
        
        # Collect scopes from all groups (union of scopes)
        scopes = set()
        for group in groups:
            group_name = group.strip() if isinstance(group, str) else str(group)
            if group_name in SCOPE_MAPPINGS:
                scopes.update(SCOPE_MAPPINGS[group_name])
                logger.info(f"Added scopes from group '{group_name}': {SCOPE_MAPPINGS[group_name]}")
            else:
                logger.warning(f"Unknown group: {group_name}")
        
        # Convert to space-separated string (OAuth 2.0 scope format)
        scope_string = ' '.join(sorted(scopes))
        logger.info(f"Final scope string: '{scope_string}'")
        
        # V2 format: Inject scopes into claimsAndScopeOverrideDetails
        # Ensure response exists and is a dict
        if 'response' not in event or event['response'] is None:
            event['response'] = {}
        
        if 'claimsAndScopeOverrideDetails' not in event['response'] or event['response']['claimsAndScopeOverrideDetails'] is None:
            event['response']['claimsAndScopeOverrideDetails'] = {}
        
        # --- ID Token: add scope as a custom claim ---
        if 'idTokenGeneration' not in event['response']['claimsAndScopeOverrideDetails'] or event['response']['claimsAndScopeOverrideDetails']['idTokenGeneration'] is None:
            event['response']['claimsAndScopeOverrideDetails']['idTokenGeneration'] = {}
        
        if 'claimsToAddOrOverride' not in event['response']['claimsAndScopeOverrideDetails']['idTokenGeneration'] or event['response']['claimsAndScopeOverrideDetails']['idTokenGeneration']['claimsToAddOrOverride'] is None:
            event['response']['claimsAndScopeOverrideDetails']['idTokenGeneration']['claimsToAddOrOverride'] = {}
        
        # Add scope claim to ID token
        event['response']['claimsAndScopeOverrideDetails']['idTokenGeneration']['claimsToAddOrOverride']['scope'] = scope_string
        
        # --- Access Token: add scopes so require_scopes() can validate them ---
        if 'accessTokenGeneration' not in event['response']['claimsAndScopeOverrideDetails'] or event['response']['claimsAndScopeOverrideDetails']['accessTokenGeneration'] is None:
            event['response']['claimsAndScopeOverrideDetails']['accessTokenGeneration'] = {}
        
        if 'claimsToAddOrOverride' not in event['response']['claimsAndScopeOverrideDetails']['accessTokenGeneration'] or event['response']['claimsAndScopeOverrideDetails']['accessTokenGeneration']['claimsToAddOrOverride'] is None:
            event['response']['claimsAndScopeOverrideDetails']['accessTokenGeneration']['claimsToAddOrOverride'] = {}
        
        # Add custom_scopes claim to access token (Cognito V2 allows this)
        event['response']['claimsAndScopeOverrideDetails']['accessTokenGeneration']['claimsToAddOrOverride']['custom_scopes'] = scope_string
        
        # Also add scopes to the access token's scopesToAdd list
        if 'scopesToAdd' not in event['response']['claimsAndScopeOverrideDetails']['accessTokenGeneration'] or event['response']['claimsAndScopeOverrideDetails']['accessTokenGeneration']['scopesToAdd'] is None:
            event['response']['claimsAndScopeOverrideDetails']['accessTokenGeneration']['scopesToAdd'] = []
        
        event['response']['claimsAndScopeOverrideDetails']['accessTokenGeneration']['scopesToAdd'] = list(scopes)
        
        logger.info(f"Modified event response: {json.dumps(event['response'], default=str)}")
        logger.info("✅ Successfully injected scopes into token")
        return event
        
    except Exception as e:
        logger.error(f"❌ Error in pre-token generation: {str(e)}", exc_info=True)
        # Return event unchanged on error to avoid blocking authentication
        return event
