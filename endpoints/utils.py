"""Shared utilities for Lambda functions."""
import json
import os
import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any


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
        valid_step_types = ['navigation', 'validation', 'secret']
        for i, step in enumerate(data['steps']):
            if 'sort' not in step or step['sort'] <= 0:
                errors.append(f'steps[{i}].sort must be a positive integer')
            if not step.get('instruction'):
                errors.append(f'steps[{i}].instruction is required')
            if step.get('step_type') not in valid_step_types:
                errors.append(f'steps[{i}].step_type must be one of: navigation, validation, secret')
    
    is_valid = len(errors) == 0
    return is_valid, errors, data if is_valid else None
