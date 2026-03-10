import json
import os
import time
import boto3
from utils import (create_response, get_current_timestamp, validate_title, 
                   validate_url, validate_user_journey, sanitize_and_fix_json,
                   validate_generated_json, require_scopes)

bedrock_runtime = boto3.client('bedrock-runtime')





def create_prompt(title, starting_url, user_journey, region):
    """Create the prompt for Amazon Bedrock based on the user journey."""
    current_time = get_current_timestamp()
    
    # Escape quotes for JSON safety
    escaped_title = title.replace('"', '\\"')
    escaped_journey = user_journey.replace('"', '\\"')
    
    prompt = f'''You are an expert test automation engineer. Convert the following user journey description into a structured JSON format for automated web testing.

DESIGN PRINCIPLES:
- SIMPLICITY FIRST: Prefer the fewest steps possible. Each step should do exactly one thing. Shorter test cases are better — do not add steps that are not strictly necessary to cover the user journey.
- STEP TYPE PRIORITY: Prefer "validation" over "retrieve_value" + "assertion". Only use retrieve_value/assertion when a value must be captured and compared after a state change or reused across multiple later steps.
- CLEAR TRANSITIONS: Each navigation step must describe exactly one action with an unambiguous target element. Moving between steps should be logical and precise.

User Journey Details:
- Title: (Wizard) {title}
- Starting URL: {starting_url}
- Journey Description: {user_journey}

Generate a JSON object that matches this EXACT schema. This JSON is imported into a test automation system, so it must be perfectly formatted and valid:

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
      "instruction": "return the value for the page title or a key element confirming the page has fully loaded",
      "step_type": "validation",
      "secret_key": "",
      "capture_variable": "",
      "validation_type": "bool",
      "validation_operator": "exact",
      "validation_value": "true",
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
1. Generate steps covering the entire user journey. Keep the test case as short and focused as possible — every step must serve a clear purpose.
2. Include navigation steps for page interactions (clicking, typing, etc.)
3. Include validation steps for expected outcomes and assertions, only values can be asserted. the types are string, bool and number.
4. Use retrieve_value steps ONLY when a value must be stored for comparison in a later assertion step or reused across multiple steps. If you just need to check something on the current page, use a validation step instead.
5. Use assertion steps ONLY to compare a previously captured runtime variable against an expected value after a state change. Do NOT use retrieve_value + assertion as a substitute for a single validation step.
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
18. Verify the JSON is valid and can be parsed
19. Do not generate a URL step or navigation step to the starting_url. The system automatically navigates to the starting_url before step 1. Do not duplicate this.
20. Secret steps must focus an input field only.
21. Instructions must be written as instructions. Like "click the search button" or "Return the amount of items in the basket"
22. The FIRST step of every use case MUST be a validation step that confirms the page has fully loaded (e.g. verifying a key heading, title, or element is visible). This ensures all subsequent steps operate on a stable, fully rendered page.
23. Every retrieve_value step should be followed by at least one assertion step that references the captured variable. Do not generate a retrieve_value step without a corresponding assertion that uses it. If the value only needs to be checked once and not compared after a state change, use a validation step instead.

Step Type Guidelines:
- "navigation": For clicking buttons, filling forms, navigating pages. Each step should describe exactly one interaction.
- "validation": PREFERRED for any check. For checking page content, verifying elements exist. Reads a value from the live page and compares it. Use this instead of retrieve_value + assertion whenever possible.
- "secret": For using stored credentials (set secret_key field)
- "retrieve_value": ONLY use when the value must be stored for later comparison after a state change or reused in multiple assertion steps. Do NOT use just to read and immediately check a value — use validation instead.
- "assertion": ONLY use to compare a previously captured runtime variable. Requires a preceding retrieve_value step. Do NOT use as a substitute for validation.
- "url": For navigating directly to a specific URL (instruction is the URL). Do not use to navigate to the starting_url.
- "download": For downloading a file from the page

DO / DON'T Examples:

DON'T: retrieve_value to capture a button label, then assertion to check it equals "Submit"
DO: Use a single validation step: "return the value for the submit button label" with validation_type "string" and validation_value "Submit"

DON'T: Use a URL step to navigate to the starting_url as the first step
DO: Start with a validation step confirming the page has loaded, e.g. "return the value for the page heading being visible"

DON'T: Split a single check into retrieve_value + assertion when the value is only needed once
DO: Use validation to check the value directly on the page

DO: Use retrieve_value + assertion when you need to capture a count before an action, perform the action, then capture and compare the count after
DO: Use retrieve_value when the same value needs to be referenced in multiple later assertion steps

Variables:
- Variables are user-defined key-value pairs listed in the "variables" array. They are referenced in step instructions using {{VariableName}} syntax and resolved at runtime before the step executes.
- Use variables for strings that appear in multiple steps to avoid repetition and keep the test DRY. Define the value once in the variables array and reference it everywhere with {{VariableName}}.
- Use variables for key elements that make the test reusable with different inputs (e.g., a sorting mode, a search term, or a category name that someone might want to test with different values).
- Use the built-in {{UniqueID}} variable when creating resources that need unique names to avoid collisions across test runs (e.g., "[QA Test] {{UniqueID}}").
- Do NOT create variables for strings that only appear once and are not a parameterizable key element. Static values like button labels, menu item names, or fixed URLs should be hardcoded directly in the instruction.
- Other built-in variables available without definition: {{Time}}, {{ExecutionID}}, {{CreatedAt}}.

Generate the complete, valid JSON now:'''
    
    return prompt

def invoke_bedrock(title, starting_url, user_journey, region, model_id):
    """Make a single call to Amazon Bedrock using the Converse API."""
    start_time = time.time()

    # Create the prompt
    prompt = create_prompt(title, starting_url, user_journey, region)
    print(f'Invoking Amazon Bedrock model {model_id} with prompt length: {len(prompt)}')

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
        print(f'Amazon Bedrock model invocation completed in {duration:.2f}s')

        # Extract the generated content
        content = response['output']['message']['content']
        if not content:
            raise Exception('Invalid response format from Amazon Bedrock: no content')

        generated_text = content[0].get('text', '')
        if not generated_text:
            raise Exception('Invalid response format from Amazon Bedrock: no text')

        # Clean up the generated text to extract JSON
        generated_json = extract_json(generated_text)

        print(f'Successfully generated JSON from Amazon Bedrock (length: {len(generated_json)} chars)')

        return generated_json

    except Exception as e:
        duration = time.time() - start_time
        print(f'Amazon Bedrock model invocation failed after {duration:.2f}s: {str(e)}')
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
    Generate a usecase from a user journey description using Amazon Bedrock AI.
    
    Request Body:
    - title: Title for the usecase (required)
    - starting_url: Starting URL for the test (required)
    - userJourney: Description of the user journey (required)
    - region: AWS region for execution (required)
    
    Returns:
    - 200: Usecase generated successfully
    - 400: Validation failed
    - 401: Authentication failed
    - 502: Amazon Bedrock service error
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
    
    # Get Amazon Bedrock model ID
    model_id = os.environ.get('BEDROCK_MODEL_ID')
    if not model_id:
        return create_response(500, {
            'success': False,
            'message': 'Configuration error',
            'error': 'Amazon Bedrock service configuration is invalid',
            'code': 'BEDROCK_CONFIG_ERROR'
        })
    
    # Generate the usecase using Amazon Bedrock
    try:
        print(f'[INFO] [{request_id}] Calling Amazon Bedrock service to generate usecase')
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
        print(f'[ERROR] [{request_id}] Amazon Bedrock service call failed: {error_msg}')
        
        # Categorize Amazon Bedrock errors
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
