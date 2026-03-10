"""
Lambda authorizer for API Gateway that validates both user tokens and M2M tokens.
Validates JWT tokens from Cognito User Pool with signature verification.
"""
import json
import os
import logging
from typing import Any, Dict
import base64
import urllib.request
from urllib.error import URLError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Cache for JWKS
jwks_cache = None

# Group-to-scope mapping for user access tokens.
# Cognito Lite tier does not include resource server scopes in the access token's
# scope claim for authorization code flow (user tokens). We resolve scopes from
# cognito:groups instead, which is present in the access token.
# This mapping must stay in sync with pre_token_generation.py SCOPE_MAPPINGS.
GROUP_SCOPE_MAPPINGS = {
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
        'api/admin',
    ],
}


def resolve_scopes_from_groups(groups: list) -> set:
    """
    Resolve OAuth scopes from Cognito group membership.

    Args:
        groups: List of Cognito group names from the cognito:groups claim.

    Returns:
        Set of scope strings derived from group membership.
    """
    scopes = set()
    for group in groups:
        group_name = group.strip() if isinstance(group, str) else str(group)
        if group_name in GROUP_SCOPE_MAPPINGS:
            scopes.update(GROUP_SCOPE_MAPPINGS[group_name])
    return scopes

# Import JWT libraries
try:
    import jwt
    from jwt.algorithms import RSAAlgorithm
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    logger.warning("PyJWT not available, signature verification disabled")


def get_jwks():
    """Get JWKS from Cognito."""
    global jwks_cache
    if jwks_cache is None:
        region = os.environ.get('AWS_REGION', 'us-east-1')
        user_pool_id = os.environ.get('USER_POOL_ID')
        jwks_url = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json"
        
        try:
            # URL is constructed from trusted env vars (AWS_REGION, USER_POOL_ID),
            # not user input — safe from SSRF.
            with urllib.request.urlopen(jwks_url) as response:  # nosec B310
                jwks_cache = json.loads(response.read().decode())
        except URLError as e:
            logger.error(f"Failed to fetch JWKS: {str(e)}")
            raise
    
    return jwks_cache


def get_signing_key(token: str) -> str:
    """Get the public key for verifying the token signature."""
    try:
        # Decode header to get kid
        header = token.split('.')[0]
        header += '=' * (4 - len(header) % 4)
        decoded_header = json.loads(base64.urlsafe_b64decode(header))
        kid = decoded_header.get('kid')
        
        if not kid:
            raise ValueError("No kid in token header")
        
        # Get JWKS and find matching key
        jwks = get_jwks()
        for key in jwks.get('keys', []):
            if key.get('kid') == kid:
                # Convert JWK to PEM format
                if JWT_AVAILABLE:
                    public_key = RSAAlgorithm.from_jwk(json.dumps(key))
                    return public_key
                else:
                    # Return the key data for manual verification if needed
                    return key
        
        raise ValueError(f"No matching key found for kid: {kid}")
    except Exception as e:
        logger.error(f"Failed to get signing key: {str(e)}")
        raise


def decode_and_verify_token(token: str, region: str, user_pool_id: str) -> Dict:
    """Decode and verify JWT token."""
    if not JWT_AVAILABLE:
        # Fallback to basic decoding without signature verification
        logger.warning("Signature verification skipped - PyJWT not available")
        parts = token.split('.')
        if len(parts) != 3:
            raise ValueError("Invalid token format")
        
        payload = parts[1]
        payload += '=' * (4 - len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    
    # Full verification with PyJWT
    try:
        # Get signing key
        signing_key = get_signing_key(token)
        
        # Verify and decode token
        expected_issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
        
        decoded_token = jwt.decode(
            token,
            signing_key,
            algorithms=['RS256'],
            options={
                'verify_signature': True,
                'verify_exp': True,
                'verify_iat': True,
                'require': ['exp', 'iat', 'iss']
            },
            issuer=expected_issuer
        )
        
        return decoded_token
    except jwt.ExpiredSignatureError:
        logger.warning("Token has expired")
        raise
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Token verification failed: {str(e)}")
        raise


def generate_policy(principal_id: str, effect: str, resource: str, context: Dict = None) -> Dict:
    """
    Generate IAM policy for API Gateway.
    
    Args:
        principal_id: User or client identifier
        effect: 'Allow' or 'Deny'
        resource: API Gateway resource ARN
        context: Additional context to pass to the Lambda
        
    Returns:
        IAM policy document
    """
    # Allow access to all methods in the API (wildcard)
    # This prevents issues with resource ARN caching
    resource_parts = resource.split('/')
    if len(resource_parts) >= 2:
        # Convert specific resource to wildcard: arn:aws:execute-api:region:account:api-id/stage/*/*
        base_arn = '/'.join(resource_parts[:2])
        wildcard_resource = f"{base_arn}/*/*"
    else:
        wildcard_resource = resource
    
    policy = {
        'principalId': principal_id,
        'policyDocument': {
            'Version': '2012-10-17',
            'Statement': [{
                'Action': 'execute-api:Invoke',
                'Effect': effect,
                'Resource': wildcard_resource
            }]
        }
    }
    
    if context:
        policy['context'] = context
    
    return policy


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda authorizer handler.
    Validates JWT tokens from Cognito and returns IAM policy.
    
    Args:
        event: API Gateway authorizer request event
        context: Lambda context
        
    Returns:
        IAM policy allowing or denying access
    """
    try:
        logger.info(f"Authorizer invoked with event: {json.dumps(event)}")
        
        # Extract token from Authorization header
        token = event.get('authorizationToken', '')
        
        if not token:
            logger.warning("No authorization token provided")
            raise Exception('Unauthorized')
        
        # Remove 'Bearer ' prefix if present
        if token.startswith('Bearer '):
            token = token[7:]
        
        logger.info(f"Token extracted (first 20 chars): {token[:20]}...")
        
        # Get environment variables
        region = os.environ.get('AWS_REGION', 'us-east-1')
        user_pool_id = os.environ.get('USER_POOL_ID')
        
        logger.info(f"Region: {region}, User Pool ID: {user_pool_id}")
        
        if not user_pool_id:
            logger.error("USER_POOL_ID environment variable not set")
            raise Exception('Unauthorized')
        
        # Validate token
        try:
            logger.info("Starting token validation...")
            # Decode and verify token with signature verification
            decoded_token = decode_and_verify_token(token, region, user_pool_id)
            logger.info(f"Token decoded successfully: {json.dumps(decoded_token, default=str)}")
            
            # Verify token use
            token_use = decoded_token.get('token_use')
            if token_use not in ['access', 'id']:
                logger.warning(f"Invalid token_use: {token_use}")
                raise Exception('Unauthorized')
            
            # Extract identity information
            client_id = decoded_token.get('client_id')
            email = decoded_token.get('email')
            username = decoded_token.get('username')
            sub = decoded_token.get('sub')
            scope = decoded_token.get('scope', '')
            cognito_groups = decoded_token.get('cognito:groups', [])
            
            logger.info(f"Token claims - email: {email}, username: {username}, client_id: {client_id}, scope: '{scope}', groups: {cognito_groups}")
            
            # Determine identity type
            if email:
                # User token
                principal_id = email
                identity_type = 'user'
            elif username:
                # User token without email
                principal_id = username
                identity_type = 'user'
            elif client_id and not email and not username:
                # M2M token (client credentials flow)
                principal_id = client_id
                identity_type = 'client'
            else:
                # Unknown token type
                logger.warning(f"Unknown token type - no clear identity")
                raise Exception('Unauthorized')
            
            # For user tokens, resolve API scopes from cognito:groups.
            # Cognito Lite tier does not put resource server scopes in the
            # access token's scope claim for authorization code flow, so we
            # derive them from group membership instead.
            if identity_type == 'user' and cognito_groups:
                group_scopes = resolve_scopes_from_groups(cognito_groups)
                # Merge with any scopes already in the token
                existing_scopes = set(scope.split()) if scope else set()
                all_scopes = existing_scopes | group_scopes
                scope = ' '.join(sorted(all_scopes))
                logger.info(f"Resolved scopes from groups {cognito_groups}: {group_scopes}")
            
            logger.info(f"Authorized: {principal_id} (type: {identity_type}, scopes: {scope})")
            
            # Generate allow policy with context
            # Note: All context values must be strings for API Gateway
            policy = generate_policy(
                principal_id=principal_id,
                effect='Allow',
                resource=event['methodArn'],
                context={
                    'identity': str(principal_id),
                    'identityType': str(identity_type),
                    'sub': str(sub or ''),
                    'clientId': str(client_id or ''),
                    'email': str(email or ''),
                    'username': str(username or ''),
                    'scope': str(scope)
                }
            )
            
            return policy
            
        except ValueError as e:
            logger.warning(f"Invalid token format: {str(e)}")
            raise Exception('Unauthorized')
        except Exception as e:
            logger.error(f"Error validating token: {str(e)}", exc_info=True)
            raise Exception('Unauthorized')
    
    except Exception as e:
        logger.error(f"Authorization failed: {str(e)}")
        # Return deny policy
        return generate_policy('user', 'Deny', event['methodArn'])
