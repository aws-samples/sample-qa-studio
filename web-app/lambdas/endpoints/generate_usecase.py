import json
import os
import time
import boto3
from utils import (create_response, get_current_timestamp, validate_title, 
                   validate_url, validate_user_journey, sanitize_and_fix_json,
                   validate_generated_json, require_scopes)

bedrock_runtime = boto3.client('bedrock-runtime')





def create_prompt(title, starting_url, user_journey, region):
    """Create the prompt for Bedrock based on the user journey."""
    current_time = get_current_timestamp()
    
    # Escape quotes for JSON safety
    escaped_title = title.replace('"', '\\"')
    escaped_journey = user_journey.replace('"', '\\"')
    
    prompt = f'''You are an expert test automation engineer. Convert the following user journey description into a structured JSON format for automated web testing.

User Journey Details:
- Title: (Wizard) {title}
- Starting URL: {starting_url}
- Journey Description: {user_journey}

Generate a JSON object that matches this EXACT schema. This JSON will be imported into a test automation system, so it must be perfectly formatted and valid:

{{
  "exportVersion": "1.0",
  "exportedAt": "{current_time}",
  "usecase": {{
    "name": "{escaped_title}",
    "description": "Generated from user journey: {escaped_journey}",
    "starting_url": "{starting_url}",
    "active": true,
    "executing_region": "{region}",
    "tags": []
  }},
  "steps": [
    {{
      "sort": 1,
      "instruction": "Navigate to the starting page",
      "step_type": "navigation",
      "secret_key": "",
      "capture_variable": "",
      "validation_type": "",
      "validation_operator": "",
      "validation_value": "",
      "assertion_variable": "",
      "value_step": "",
      "value_type": ""
    }}
  ],
  "variables": [],
  "secrets": [],
  "hooks": null
}}

CRITICAL REQUIREMENTS:
1. Generate comprehensive steps covering the entire user journey
2. Include navigation steps for page interactions (clicking, typing, etc.)
3. Include validation steps for expected outcomes and assertions, only values can be asserted. the types are string, bool and number.
4. Use retrieve_value steps to capture values from the page into runtime variables for later use.
5. Use assertion steps to compare previously captured runtime variables against expected values without interacting with the browser.
6. Use ONLY these step types: "navigation", "validation", "secret", "retrieve_value", "assertion", "url", "download"
7. Validation and assertion operators for string are exact, exact_case_insensitive, contains, contains_case_insensitive and not_equal
8. Validation and assertion operators for bool are exact
9. Validation and assertion operators for number are equals, less_then, greater_then, greater_or_equal_then and less_or_equal_then
10. Validation step instruction must start with "return the value for ...". like: "return the number of products on the page".
11. Retrieve value step instruction must describe what value to extract from the page. Set capture_variable to the variable name and value_type to "string", "number", or "bool".
12. Assertion steps do NOT interact with the browser. Set assertion_variable to the name of a previously captured runtime variable, and set validation_type, validation_operator, and validation_value for the comparison.
13. URL step instruction must be a valid URL to navigate to directly.
14. Each step MUST have ALL fields present, use empty strings ("") for unused fields
15. Sort steps sequentially starting from 1 (no gaps or duplicates)
16. All strings must be properly escaped for JSON
17. Return ONLY the JSON object, no markdown, no explanations, no additional text
18. Ensure the JSON is valid and can be parsed
19. You do not need a step to move to the start page.
20. Secret steps must always focus an input field only.
21. Instructions must be written as instructions. Like "click the search button" or "Return the amount of items in the basket"

Step Type Guidelines:
- "navigation": For clicking buttons, filling forms, navigating pages
- "validation": For checking page content, verifying elements exist. Reads a value from the live page and compares it.
- "secret": For using stored credentials (set secret_key field)
- "retrieve_value": For extracting a value from the page and storing it as a runtime variable (set capture_variable and value_type fields)
- "assertion": For comparing a previously captured runtime variable against an expected value without browser interaction (set assertion_variable, validation_type, validation_operator, validation_value fields)
- "url": For navigating directly to a specific URL (instruction is the URL)
- "download": For downloading a file from the page

Generate the complete, valid JSON now:'''
    
    return prompt

def invoke_bedrock(title, starting_url, user_journey, region, model_id):
    """Make a single call to Bedrock using the Converse API."""
    start_time = time.time()

    # Create the prompt
    prompt = create_prompt(title, starting_url, user_journey, region)
    print(f'Invoking Bedrock model {model_id} with prompt length: {len(prompt)}')

    try:
        response = bedrock_runtime.converse(
            modelId=model_id,
            messages=[{
                'role': 'user',
                'content': [{'text': prompt}]
            }],
            inferenceConfig={
                'maxTokens': 4096,
                'temperature': 0.1,
            }
        )

        duration = time.time() - start_time
        print(f'Bedrock model invocation completed in {duration:.2f}s')

        # Extract the generated content
        content = response['output']['message']['content']
        if not content:
            raise Exception('Invalid response format from Bedrock: no content')

        generated_text = content[0].get('text', '')
        if not generated_text:
            raise Exception('Invalid response format from Bedrock: no text')

        # Clean up the generated text to extract JSON
        generated_json = extract_json(generated_text)

        print(f'Successfully generated JSON from Bedrock (length: {len(generated_json)} chars)')

        return generated_json

    except Exception as e:
        duration = time.time() - start_time
        print(f'Bedrock model invocation failed after {duration:.2f}s: {str(e)}')
        raise

def extract_json(text):
    """Extract JSON from the generated text."""
    # Remove common markdown artifacts
    text = text.replace('```json', '').replace('```', '').strip()
    
    # Find the first opening brace
    start = text.find('{')
    if start == -1:
        print('No opening brace found in generated text')
        return text
    
    # Find the matching closing brace by counting braces
    brace_count = 0
    end = -1
    for i in range(start, len(text)):
        if text[i] == '{':
            brace_count += 1
        elif text[i] == '}':
            brace_count -= 1
            if brace_count == 0:
                end = i
                break
    
    if end == -1:
        # Fallback to last brace
        end = text.rfind('}')
        if end == -1 or end <= start:
            return text
    
    extracted = text[start:end+1]
    print(f'Extracted JSON from position {start} to {end} (length: {len(extracted)})')
    return extracted



def get_error_code(error_message):
    """Map error messages to error codes."""
    error_lower = error_message.lower()
    
    if 'required' in error_lower:
        return 'REQUIRED_FIELD'
    if 'characters or less' in error_lower or 'exceeded' in error_lower:
        return 'MAX_LENGTH_EXCEEDED'
    if 'at least' in error_lower or 'minimum' in error_lower:
        return 'MIN_LENGTH_NOT_MET'
    if 'invalid' in error_lower or 'format' in error_lower:
        return 'INVALID_FORMAT'
    if 'url' in error_lower:
        return 'INVALID_URL'
    if 'security' in error_lower or 'threat' in error_lower or 'dangerous' in error_lower:
        return 'SECURITY_VIOLATION'
    
    return 'VALIDATION_ERROR'


def handler(event, context):
    """
    Generate a usecase from a user journey description using Bedrock AI.
    
    Request Body:
    - title: Title for the usecase (required)
    - starting_url: Starting URL for the test (required)
    - userJourney: Description of the user journey (required)
    - region: AWS region for execution (required)
    
    Returns:
    - 200: Usecase generated successfully
    - 400: Validation failed
    - 401: Authentication failed
    - 502: Bedrock service error
    - 500: Internal server error
    """
    request_id = event.get('requestContext', {}).get('requestId', f'req-{int(time.time() * 1000)}')
    
    print(f'[INFO] [{request_id}] Received request')
    
    # Validate scope authorization
    user_identity, error = require_scopes(event, ['api/usecases.write'])
    if error:
        return error
    
    # Extract user info
    user_email = user_identity.get('email') or user_identity.get('identity', 'unknown')
    
    print(f'[INFO] [{request_id}] Processing generate usecase request for user {user_email}')
    
    # Parse request body
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return create_response(400, {
            'success': False,
            'message': 'Invalid request format',
            'error': 'Request body must be valid JSON',
            'code': 'INVALID_JSON'
        })
    
    title = body.get('title', '')
    starting_url = body.get('starting_url', '') or body.get('startingUrl', '')
    user_journey = body.get('userJourney', '') or body.get('user_journey', '')
    region = body.get('region', '')
    
    # Validate inputs
    validation_errors = []
    
    # Validate title
    sanitized_title, title_errors = validate_title(title)
    if title_errors:
        for error in title_errors:
            validation_errors.append({
                'field': 'title',
                'message': error,
                'code': get_error_code(error)
            })
    else:
        title = sanitized_title
    
    # Validate URL
    sanitized_url, url_errors = validate_url(starting_url)
    if url_errors:
        for error in url_errors:
            validation_errors.append({
                'field': 'starting_url',
                'message': error,
                'code': get_error_code(error)
            })
    else:
        starting_url = sanitized_url
    
    # Validate user journey
    sanitized_journey, journey_errors = validate_user_journey(user_journey)
    if journey_errors:
        for error in journey_errors:
            validation_errors.append({
                'field': 'userJourney',
                'message': error,
                'code': get_error_code(error)
            })
    else:
        user_journey = sanitized_journey
    
    # Validate region
    if not region.strip():
        validation_errors.append({
            'field': 'region',
            'message': 'Region is required',
            'code': 'REQUIRED'
        })
    else:
        valid_regions = ['us-east-1', 'us-west-2', 'ap-southeast-2', 'eu-central-1']
        if region not in valid_regions:
            validation_errors.append({
                'field': 'region',
                'message': f'Invalid region. Must be one of: {", ".join(valid_regions)}',
                'code': 'INVALID_FORMAT'
            })
    
    if validation_errors:
        return create_response(400, {
            'success': False,
            'message': 'Request validation failed',
            'error': '; '.join([e['message'] for e in validation_errors]),
            'code': 'VALIDATION_ERROR',
            'details': {'validationErrors': validation_errors}
        })
    
    # Get Bedrock model ID
    model_id = os.environ.get('BEDROCK_MODEL_ID')
    if not model_id:
        return create_response(500, {
            'success': False,
            'message': 'Configuration error',
            'error': 'Bedrock service configuration is invalid',
            'code': 'BEDROCK_CONFIG_ERROR'
        })
    
    # Generate the usecase using Bedrock
    try:
        print(f'[INFO] [{request_id}] Calling Bedrock service to generate usecase')
        generated_json = invoke_bedrock(title, starting_url, user_journey, region, model_id)
        
        # Sanitize and validate the generated JSON
        print(f'[INFO] [{request_id}] Sanitizing and validating generated JSON')
        sanitized_json = sanitize_and_fix_json(generated_json)
        is_valid, errors, schema = validate_generated_json(sanitized_json)
        
        if not is_valid:
            print(f'[ERROR] [{request_id}] Generated JSON validation failed: {errors}')
            return create_response(502, {
                'success': False,
                'message': 'AI service error',
                'error': f'Generated test case validation failed: {"; ".join(errors)}',
                'code': 'INVALID_GENERATED_JSON'
            })
        
        # Log export version and full JSON for debugging
        export_version = schema.get('exportVersion', 'NOT_FOUND') if schema else 'NO_SCHEMA'
        print(f'[INFO] [{request_id}] Export version: {export_version}')
        print(f'[DEBUG] [{request_id}] Generated JSON: {sanitized_json}')
        
        steps_count = len(schema.get('steps', [])) if schema else 0
        print(f'[INFO] [{request_id}] JSON validation successful, {steps_count} steps generated')
        
        return create_response(200, {
            'success': True,
            'usecaseData': sanitized_json,
            'message': 'Test case generated successfully'
        })
        
    except Exception as e:
        error_msg = str(e)
        print(f'[ERROR] [{request_id}] Bedrock service call failed: {error_msg}')
        
        # Categorize Bedrock errors
        error_code = 'BEDROCK_ERROR'
        message = 'Failed to generate test case'
        
        if 'throttling' in error_msg.lower() or 'rate limit' in error_msg.lower():
            error_code = 'RATE_LIMIT_EXCEEDED'
            message = 'AI service is currently busy. Please try again in a moment'
        elif 'timeout' in error_msg.lower():
            error_code = 'TIMEOUT_ERROR'
            message = 'AI service request timed out. Please try again'
        elif 'access denied' in error_msg.lower() or 'unauthorized' in error_msg.lower():
            error_code = 'ACCESS_DENIED'
            message = 'AI service access denied'
        
        return create_response(502, {
            'success': False,
            'message': message,
            'error': error_msg,
            'code': error_code
        })
