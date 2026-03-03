"""Shared utilities for Lambda functions."""
import json
import os
import logging
import time
import secrets
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any


def generate_uuid7() -> str:
    """
    Generate a UUIDv7 (time-ordered UUID).
    
    UUIDv7 format:
    - 48 bits: Unix timestamp in milliseconds
    - 12 bits: sub-millisecond precision / sequence counter
    - 2 bits: variant (10)
    - 6 bits: version (0111 = 7)
    - 62 bits: random data
    
    Returns:
        String representation of UUIDv7
    """
    # Get current timestamp in milliseconds
    timestamp_ms = int(time.time() * 1000)
    
    # Generate random bytes for the rest
    random_bytes = secrets.token_bytes(10)
    
    # Build the UUID
    # First 48 bits: timestamp
    uuid_int = timestamp_ms << 80
    
    # Next 12 bits: sub-ms precision (use random for simplicity)
    uuid_int |= (random_bytes[0] & 0x0F) << 76
    uuid_int |= random_bytes[1] << 68
    
    # Version (4 bits) = 7
    uuid_int |= 0x7 << 76
    
    # Variant (2 bits) = 10
    uuid_int |= 0x2 << 62
    
    # Remaining random bits
    for i in range(2, 10):
        uuid_int |= random_bytes[i] << ((9 - i) * 8)
    
    # Format as UUID string
    hex_str = f'{uuid_int:032x}'
    return f'{hex_str[0:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:32]}'


class DynamoDBEncoder(json.JSONEncoder):
    """Custom JSON encoder for DynamoDB data types."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        if isinstance(obj, set):
            return list(obj)
        return super().default(obj)


def get_table_name() -> str:
    """Get DynamoDB table name from environment variable."""
    table_name = os.environ.get('TABLE_NAME')
    if not table_name:
        logging.warning("environment variable 'TABLE_NAME' missing")
        return 'accept-ai'
    return table_name


def get_secret_prefix() -> str:
    """Get secret prefix from environment variable."""
    secret_prefix = os.environ.get('SECRET_PREFIX')
    if not secret_prefix:
        logging.warning("environment variable 'SECRET_PREFIX' missing")
        return 'accept-ai'
    return secret_prefix


def get_bucket_name() -> str:
    """Get S3 bucket name from environment variable."""
    bucket_name = os.environ.get('BUCKET_NAME')
    if not bucket_name:
        logging.warning("environment variable 'BUCKET_NAME' missing")
        return 'accept-ai-artefacts'
    return bucket_name


def get_current_timestamp() -> str:
    """
    Get current timestamp in RFC3339 format (compatible with Go's time.RFC3339).
    Format: 2006-01-02T15:04:05Z
    """
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def extract_user_identity(event: dict) -> dict:
    """
    Extract user identity from API Gateway event.
    Handles both user tokens (with email) and M2M tokens (client credentials).
    Supports both Cognito authorizer and Lambda authorizer formats.
    
    By default, this function REJECTS M2M tokens with a 403 error.
    Use allow_m2m_token() instead if you want to allow M2M tokens.
    
    Args:
        event: API Gateway proxy request event
        
    Returns:
        Dictionary with:
        - identity: Email for user tokens, client_id for M2M tokens
        - identity_type: 'user' or 'client'
        - sub: Cognito sub claim
        - client_id: Client ID for M2M tokens (optional)
        - email: Email for user tokens (optional)
        - scopes: List of OAuth scopes for M2M tokens (optional)
    """
    request_context = event.get('requestContext', {})
    authorizer = request_context.get('authorizer', {})
    
    logging.info(f"=== EXTRACTING USER IDENTITY ===")
    logging.info(f"Full authorizer object: {json.dumps(authorizer, default=str)}")
    
    # Check if using Lambda authorizer (context is directly in authorizer)
    # or Cognito authorizer (context is in claims)
    if 'claims' in authorizer:
        # Cognito authorizer format
        claims = authorizer.get('claims', {})
        logging.info("Using Cognito authorizer format (claims)")
    else:
        # Lambda authorizer format - context is directly in authorizer
        claims = authorizer
        logging.info("Using Lambda authorizer format (direct context)")
    
    logging.info(f"Claims extracted: {json.dumps(claims, default=str)}")
    
    email = claims.get('email')
    username = claims.get('username')
    sub = claims.get('sub', '')
    client_id = claims.get('clientId') or claims.get('client_id')
    identity_type = claims.get('identityType') or claims.get('identity_type')
    scope = claims.get('scope', '')
    
    logging.info(f"Parsed values - email: {email}, username: {username}, sub: {sub}, client_id: {client_id}, identity_type: {identity_type}, scope: {scope}")
    
    # Parse scopes (space-separated string)
    scopes = scope.split() if scope else []
    
    # Use identity_type from authorizer if available
    if identity_type == 'client':
        result = {
            'identity': client_id or sub,
            'identity_type': 'client',
            'sub': sub,
            'client_id': client_id,
            'scopes': scopes
        }
        logging.info(f"Identified as CLIENT: {result}")
        return result
    elif identity_type == 'user':
        result = {
            'identity': email or username or sub,
            'identity_type': 'user',
            'sub': sub,
            'email': email,
            'scopes': scopes  # Include scopes for user tokens too
        }
        logging.info(f"Identified as USER: {result}")
        return result
    
    # Fallback: determine from claims
    # M2M token (client credentials flow)
    if client_id and not email and not username:
        result = {
            'identity': client_id,
            'identity_type': 'client',
            'sub': sub,
            'client_id': client_id,
            'scopes': scopes
        }
        logging.info(f"Fallback identified as CLIENT: {result}")
        return result
    
    # User token
    if email or username:
        result = {
            'identity': email or username,
            'identity_type': 'user',
            'sub': sub,
            'email': email,
            'scopes': scopes  # Include scopes for user tokens too
        }
        logging.info(f"Fallback identified as USER: {result}")
        return result
    
    # Unknown token type
    result = {
        'identity': sub or 'unknown',
        'identity_type': 'unknown',
        'sub': sub,
        'scopes': []
    }
    logging.warning(f"Could not identify token type - returning UNKNOWN: {result}")
    return result


def allow_m2m_token(event: dict) -> tuple[dict, dict | None]:
    """
    Validate authentication and allow both user tokens and M2M tokens.
    Use this for execution-related endpoints that should be accessible via M2M.
    
    Args:
        event: API Gateway proxy request event
        
    Returns:
        Tuple of (user_identity, error_response)
        If error_response is not None, return it immediately
    """
    user_identity = extract_user_identity(event)
    
    if user_identity['identity_type'] == 'unknown':
        return user_identity, create_response(401, {'error': 'Unauthorized'})
    
    # Allow both 'user' and 'client' identity types
    logging.info(f"Request authorized: {user_identity['identity']} (type: {user_identity['identity_type']})")
    return user_identity, None


def require_user_token(event: dict) -> tuple[dict, dict | None]:
    """
    Validate that the request is from a user token, not an M2M token.
    This is the DEFAULT validation - use this for all endpoints unless
    you explicitly want to allow M2M tokens (use allow_m2m_token instead).
    
    M2M tokens are only allowed for execution-related endpoints.
    
    Args:
        event: API Gateway proxy request event
        
    Returns:
        Tuple of (user_identity, error_response)
        If error_response is not None, return it immediately
    """
    user_identity = extract_user_identity(event)
    
    if user_identity['identity_type'] == 'client':
        logging.warning(f"M2M token attempted to access user-only endpoint: {user_identity['client_id']}")
        return user_identity, create_response(403, {
            'error': 'Forbidden',
            'message': 'M2M tokens can only access execution endpoints. Use a user token to access this endpoint.'
        })
    
    if user_identity['identity_type'] == 'unknown':
        return user_identity, create_response(401, {'error': 'Unauthorized'})
    
    logging.info(f"User authenticated: {user_identity['identity']} (type: {user_identity['identity_type']})")
    return user_identity, None


def require_scopes(event: dict, required_scopes: list[str]) -> tuple[dict, dict | None]:
    """
    Validate that the request token contains required scopes.
    Implements scope inheritance: api/admin grants all access.
    
    This function should be used by all endpoints to enforce scope-based authorization.
    It extracts scopes from the JWT token and validates them against the required scopes.
    
    Args:
        event: API Gateway proxy request event
        required_scopes: List of scope strings (e.g., ['api/usecases.read'])
        
    Returns:
        Tuple of (user_identity, error_response)
        If error_response is not None, return it immediately
        
    Example:
        user_identity, error = require_scopes(event, ['api/usecases.read'])
        if error:
            return error
    """
    # Extract user identity and scopes
    user_identity = extract_user_identity(event)
    token_scopes = user_identity.get('scopes', [])
    
    # Log scope validation attempt
    logging.info(f"Scope validation - Identity: {user_identity['identity']}, "
                f"Type: {user_identity['identity_type']}, "
                f"Token scopes: {token_scopes}, "
                f"Required: {required_scopes}")
    
    # Check for admin scope (grants all access via inheritance)
    if 'api/admin' in token_scopes:
        logging.info(f"Admin scope present - granting access")
        return user_identity, None
    
    # Check if all required scopes are present
    missing_scopes = [s for s in required_scopes if s not in token_scopes]
    
    if missing_scopes:
        logging.warning(f"Insufficient scopes - Missing: {missing_scopes}")
        return user_identity, create_response(403, {
            'error': 'Forbidden',
            'message': f'Missing required scopes: {", ".join(missing_scopes)}',
            'required_scopes': required_scopes,
            'token_scopes': token_scopes
        })
    
    logging.info(f"Scope validation passed")
    return user_identity, None


def validate_scope_access(user_scopes: list[str], required_scope: str, permission_type: str) -> None:
    """
    Validate user has required permission on scope.
    
    Supports scope patterns for test suites and use cases:
    - suite:* grants access to all suites
    - usecase:* grants access to all use cases
    - suite:{name}:* grants all permissions on specific suite
    - suite:{name}:{permission} grants specific permission
    
    Permission hierarchy:
    - write permission implies read and execute permissions
    
    Args:
        user_scopes: List of scopes from JWT token (e.g., ['suite:smoke-tests:read'])
        required_scope: Scope to check (e.g., 'suite:smoke-tests')
        permission_type: 'read', 'write', or 'execute'
    
    Raises:
        PermissionError: If user lacks required permission
        
    Example:
        validate_scope_access(['suite:smoke-tests:write'], 'suite:smoke-tests', 'read')  # OK
        validate_scope_access(['suite:smoke-tests:read'], 'suite:smoke-tests', 'write')  # Raises
    """
    if not user_scopes:
        raise PermissionError(f'User lacks {permission_type} permission on {required_scope}')
    
    # Check for wildcard access to the scope (e.g., 'suite:smoke-tests:*')
    wildcard_scope = f'{required_scope}:*'
    if wildcard_scope in user_scopes:
        logging.info(f"Wildcard scope {wildcard_scope} grants {permission_type} access")
        return
    
    # Check for specific permission (e.g., 'suite:smoke-tests:read')
    required_permission = f'{required_scope}:{permission_type}'
    if required_permission in user_scopes:
        logging.info(f"Specific permission {required_permission} grants access")
        return
    
    # Check if user has write permission (implies read and execute)
    if permission_type in ['read', 'execute']:
        write_permission = f'{required_scope}:write'
        if write_permission in user_scopes:
            logging.info(f"Write permission {write_permission} implies {permission_type} access")
            return
    
    # No matching permission found
    raise PermissionError(f'User lacks {permission_type} permission on {required_scope}')


def create_response(status_code: int, body: Any, cors: bool = True) -> dict:
    """
    Create a standardized API Gateway response.
    
    Args:
        status_code: HTTP status code
        body: Response body (will be JSON encoded)
        cors: Whether to include CORS headers
        
    Returns:
        API Gateway proxy response dictionary
    """
    headers = {'Content-Type': 'application/json'}
    
    if cors:
        headers.update({
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization'
        })
    
    return {
        'statusCode': status_code,
        'headers': headers,
        'body': json.dumps(body, cls=DynamoDBEncoder)
    }


# User journey validation utilities
import re
from urllib.parse import urlparse

def validate_title(title):
    """Validate and sanitize a title input."""
    errors = []
    
    # Sanitize
    sanitized = title.strip()
    
    # Security check
    if contains_xss(sanitized):
        errors.append('Title contains potentially dangerous content')
        return '', errors
    
    # Length validation
    if not sanitized:
        errors.append('Title is required')
        return '', errors
    
    if len(sanitized) > 200:
        errors.append('Title must be 200 characters or less')
        return '', errors
    
    if len(sanitized) < 3:
        errors.append('Title must be at least 3 characters long')
        return '', errors
    
    # Pattern validation (alphanumeric, spaces, hyphens, underscores, basic punctuation)
    if not re.match(r'^[a-zA-Z0-9\s\-_.,:()\[\]]+$', sanitized):
        errors.append('Title contains invalid characters')
        return '', errors
    
    return sanitized, errors

def validate_url(url_str):
    """Validate and sanitize a URL input."""
    errors = []
    
    # Sanitize
    sanitized = url_str.strip()
    
    # Security check
    if contains_xss(sanitized):
        errors.append('URL contains potentially dangerous content')
        return '', errors
    
    # Required validation
    if not sanitized:
        errors.append('Starting URL is required')
        return '', errors
    
    # URL format validation
    try:
        parsed = urlparse(sanitized)
        
        if parsed.scheme not in ['http', 'https']:
            errors.append('URL must start with http:// or https://')
            return '', errors
        
        if not parsed.netloc:
            errors.append('URL must include a valid host')
            return '', errors
        
        if '..' in parsed.netloc or len(parsed.netloc) < 3:
            errors.append('URL host appears to be invalid')
            return '', errors
            
    except Exception:
        errors.append('Invalid URL format')
        return '', errors
    
    return sanitized, errors

def validate_user_journey(journey):
    """Validate and sanitize a user journey description."""
    errors = []
    
    # Sanitize
    sanitized = journey.strip()
    
    # Security check
    if contains_xss(sanitized):
        errors.append('User journey contains potentially dangerous content')
        return '', errors
    
    # Required validation
    if not sanitized:
        errors.append('User journey description is required')
        return '', errors
    
    # Length validation
    if len(sanitized) < 50:
        errors.append('User journey description must be at least 50 characters')
        return '', errors
    
    if len(sanitized) > 2000:
        errors.append('User journey description must be 2000 characters or less')
        return '', errors
    
    # Content validation
    words = sanitized.split()
    if len(words) < 10:
        errors.append('User journey description should contain more detailed steps')
        return '', errors
    
    # Check for action words
    action_words = ['click', 'enter', 'navigate', 'select', 'submit', 'verify', 
                   'check', 'fill', 'choose', 'confirm', 'type', 'press', 'scroll', 'hover']
    has_actions = any(action in sanitized.lower() for action in action_words)
    
    if not has_actions:
        errors.append('User journey should include specific actions (click, enter, navigate, etc.)')
        return '', errors
    
    return sanitized, errors

def contains_xss(text):
    """Check for potential XSS content."""
    xss_patterns = [
        r'<script',
        r'javascript:',
        r'on\w+\s*=',
        r'<iframe',
        r'<object',
        r'<embed'
    ]
    
    lower_text = text.lower()
    return any(re.search(pattern, lower_text, re.IGNORECASE) for pattern in xss_patterns)

def sanitize_and_fix_json(json_str):
    """Attempt to fix common issues in generated JSON."""
    # Remove markdown code block markers
    json_str = json_str.replace('```json', '').replace('```', '')
    
    # Trim whitespace
    json_str = json_str.strip()
    
    # Ensure it starts and ends with braces
    if not json_str.startswith('{'):
        start = json_str.find('{')
        if start != -1:
            json_str = json_str[start:]
    
    if not json_str.endswith('}'):
        end = json_str.rfind('}')
        if end != -1:
            json_str = json_str[:end+1]
    
    return json_str

def validate_generated_json(json_str):
    """Validate the generated JSON against the import_usecase schema."""
    errors = []
    
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return False, [f'Invalid JSON format: {str(e)}'], None
    
    # Validate required top-level fields
    if 'exportVersion' not in data:
        errors.append('exportVersion is required')
    elif data['exportVersion'] != '1.0':
        errors.append('exportVersion must be "1.0"')
    
    if 'exportedAt' not in data:
        errors.append('exportedAt is required')
    
    if 'usecase' not in data:
        errors.append('usecase is required')
    else:
        usecase = data['usecase']
        if not usecase.get('name'):
            errors.append('usecase.name is required')
        if not usecase.get('starting_url'):
            errors.append('usecase.starting_url is required')
        if 'tags' not in usecase:
            errors.append('usecase.tags must be an array')
    
    if 'steps' not in data:
        errors.append('steps array is required')
    elif not data['steps']:
        errors.append('at least one step is required')
    else:
        valid_step_types = ['navigation', 'validation', 'secret', 'retrieve_value', 'assertion', 'url', 'download']
        for i, step in enumerate(data['steps']):
            if 'sort' not in step or step['sort'] <= 0:
                errors.append(f'steps[{i}].sort must be a positive integer')
            if not step.get('instruction'):
                errors.append(f'steps[{i}].instruction is required')
            if step.get('step_type') not in valid_step_types:
                errors.append(f'steps[{i}].step_type must be one of: {", ".join(valid_step_types)}')
    
    is_valid = len(errors) == 0
    return is_valid, errors, data if is_valid else None
