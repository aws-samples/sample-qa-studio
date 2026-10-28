"""
Lambda authorizer for API Gateway that validates both user tokens and M2M tokens.
Validates JWT tokens from Amazon Cognito user pool with signature verification.
"""
import lambda_init  # noqa: F401 — must be first import to add dependencies/ to sys.path
import json
import os
import logging
import time
from typing import Any, Dict
import base64
import urllib.request
import urllib.parse
from urllib.error import URLError

import boto3

from role_scopes import (
    scopes_for_groups, parse_group, is_admin_group, M2M_TEAM_ROLES, M2M_FORBIDDEN_SCOPES,
)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Cache for JWKS
jwks_cache = None

# Backward-compatibility alias — existing tests import GROUP_SCOPE_MAPPINGS.
# This is kept as a read-only constant; the actual resolution uses role_scopes.
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
        'api/applications.read',
        'api/applications.write',
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
        'api/applications.read',
        'api/applications.write',
        'api/teams.manage',
        'api/admin',
    ],
}


def resolve_scopes_from_groups(groups: list) -> set:
    """
    Resolve OAuth scopes from Cognito group membership.

    Delegates to the shared role_scopes module which is the single source of truth.

    Args:
        groups: List of Cognito group names from the cognito:groups claim.

    Returns:
        Set of scope strings derived from group membership.
    """
    return scopes_for_groups(groups)


def resolve_team_context(groups: list) -> list:
    """
    Extract team membership context from Cognito groups.

    Parses each group name and returns a list of dicts describing the user's
    team memberships and roles.

    Args:
        groups: List of Cognito group names from the cognito:groups claim.

    Returns:
        List of dicts with keys: 'team_id', 'role', 'group_name'.
        Only includes entries where team_id is not None (team groups).
    """
    team_roles = []
    for group in groups:
        group_name = group.strip() if isinstance(group, str) else str(group)
        parsed = parse_group(group_name)
        if parsed and parsed['team_id'] is not None:
            team_roles.append(parsed)
    return team_roles

# OAuth client -> team binding (OAUTH_CLIENTS/{client_id}.team_id/team_role),
# cached per warm container. API Gateway also caches the whole policy (5 min).
CLIENT_BINDING_TTL_SECONDS = 60
_client_binding_cache: Dict[str, tuple] = {}


def _get_clients_table():
    """DynamoDB table holding the OAUTH_CLIENTS records."""
    return boto3.resource('dynamodb').Table(os.environ['TABLE_NAME'])


def _lookup_client_binding(client_id: str) -> list:
    """
    Team binding of an M2M client as authorizer teamRoles.

    Returns:
        [{'team_id', 'role'}] for a bound client, [] when unbound, when the
        role isn't an allowed M2M role, or when the lookup fails (fail closed;
        failures are not cached).
    """
    now = time.monotonic()
    cached = _client_binding_cache.get(client_id)
    if cached and cached[0] > now:
        return cached[1]
    try:
        item = _get_clients_table().get_item(
            Key={'pk': 'OAUTH_CLIENTS', 'sk': client_id},
            ProjectionExpression='team_id, team_role',
        ).get('Item') or {}
    except Exception as e:
        logger.error(f"client_binding_lookup_failed: client_id={client_id} error={type(e).__name__}")
        return []
    team_id = item.get('team_id')
    role = item.get('team_role')
    binding = [{'team_id': team_id, 'role': role}] if team_id and role in M2M_TEAM_ROLES else []
    _client_binding_cache[client_id] = (now + CLIENT_BINDING_TTL_SECONDS, binding)
    return binding


# Import JWT libraries — fail closed if not available
try:
    import jwt
    from jwt.algorithms import RSAAlgorithm
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    logger.error("CRITICAL: PyJWT is not installed — all requests will be denied. "
                 "Ensure requirements.txt is installed into the Lambda deployment package.")


def get_jwks():
    """Get JWKS from Amazon Cognito."""
    global jwks_cache
    if jwks_cache is None:
        region = os.environ.get('AWS_REGION', 'us-east-1')
        user_pool_id = os.environ.get('USER_POOL_ID')
        jwks_url = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json"
        
        # Validate URL scheme to prevent SSRF via file:// or other schemes
        parsed = urllib.parse.urlparse(jwks_url)
        if parsed.scheme != 'https' or parsed.hostname != f"cognito-idp.{region}.amazonaws.com":
            raise ValueError("JWKS URL must be the HTTPS Cognito endpoint for this region")
        
        try:
            req = urllib.request.Request(jwks_url, method='GET')  # nosemgrep: dynamic-urllib-use-detected
            with urllib.request.urlopen(req, timeout=10) as response:  # nosec B310 nosemgrep: dynamic-urllib-use-detected - scheme/host validated above
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
                public_key = RSAAlgorithm.from_jwk(json.dumps(key))
                return public_key
        
        raise ValueError(f"No matching key found for kid: {kid}")
    except Exception as e:
        logger.error(f"Failed to get signing key: {str(e)}")
        raise


def decode_and_verify_token(token: str, region: str, user_pool_id: str) -> Dict:
    """Decode and verify JWT token with signature verification."""
    if not JWT_AVAILABLE:
        raise RuntimeError("PyJWT is not installed — cannot verify token signatures. Denying access.")
    
    try:
        signing_key = get_signing_key(token)
        expected_issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
        
        decoded_token = jwt.decode(
            token,
            signing_key,
            algorithms=['RS256'],
            options={
                'verify_signature': True,
                'verify_exp': True,
                'verify_iat': True,
                'verify_aud': False,
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
        # Never log the event: authorizationToken is the caller's bearer token.
        logger.info(f"Authorizer invoked: type={event.get('type')} methodArn={event.get('methodArn')}")
        
        # Extract token from Authorization header
        token = event.get('authorizationToken', '')
        
        if not token:
            logger.warning("No authorization token provided")
            raise Exception('Unauthorized')
        
        # Remove 'Bearer ' prefix if present
        if token.startswith('Bearer '):
            token = token[7:]
        
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
            # Claims include email/username (PII); log only opaque identifiers.
            logger.info(f"Token verified: token_use={decoded_token.get('token_use')} sub={decoded_token.get('sub')}")
            
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
            
            logger.info(f"Token claims - sub: {sub}, client_id: {client_id}, scope: '{scope}', groups: {cognito_groups}")
            
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
            team_roles = []
            is_admin = False
            if identity_type == 'user' and cognito_groups:
                group_scopes = resolve_scopes_from_groups(cognito_groups)
                # Merge with any scopes already in the token
                existing_scopes = set(scope.split()) if scope else set()
                all_scopes = existing_scopes | group_scopes
                scope = ' '.join(sorted(all_scopes))
                logger.info(f"Resolved scopes from groups {cognito_groups}: {group_scopes}")

                # Resolve team context for downstream handlers
                team_roles = resolve_team_context(cognito_groups)
                is_admin = any(is_admin_group(g.strip() if isinstance(g, str) else str(g)) for g in cognito_groups)
                logger.info(f"Team roles: {team_roles}, isAdmin: {is_admin}")
            elif identity_type == 'client':
                # M2M clients never hold studio-wide or team-management scopes,
                # even if the Cognito app client still allows them (legacy).
                scope = ' '.join(s for s in scope.split() if s not in M2M_FORBIDDEN_SCOPES)
                worker_client_id = os.environ.get('WORKER_CLIENT_ID')
                if worker_client_id and client_id == worker_client_id:
                    # The shared worker acts only through its execution capability.
                    identity_type = 'worker'
                else:
                    team_roles = _lookup_client_binding(client_id)
                logger.info(f"Client identity: type={identity_type} teamRoles={team_roles}")

            # principal_id is the email for user tokens, so log sub/client_id instead.
            logger.info(f"Authorized: {sub or client_id} (type: {identity_type}, scopes: {scope})")

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
                    'scope': str(scope),
                    'teamRoles': json.dumps(team_roles),
                    'isAdmin': str(is_admin).lower(),
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
