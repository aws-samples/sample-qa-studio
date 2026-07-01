import lambda_init  # noqa: F401 — must be first import (adds dependencies/ to sys.path)

import io
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
import boto3
from utils import (create_response, get_current_timestamp, validate_title,
                   validate_url, validate_user_journey, sanitize_and_fix_json,
                   validate_generated_json, require_scopes)
from recording_models import RecordingData, CDPRecordingPayload

logger = logging.getLogger()
logger.setLevel(logging.INFO)

bedrock_runtime = boto3.client('bedrock-runtime')


# --- JSON Schema for structured output ---
# This schema is passed to Bedrock via toolConfig (tool use with forced
# toolChoice) to guarantee the model response conforms to the UseCase
# export format via constrained decoding.

USECASE_EXPORT_SCHEMA = {
    'type': 'object',
    'properties': {
        'exportVersion': {
            'type': 'string',
            'description': 'Schema version, always "1.0"',
        },
        'exportedAt': {
            'type': 'string',
            'description': 'ISO 8601 timestamp of generation',
        },
        'usecase': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string', 'description': 'Use case title'},
                'description': {'type': 'string', 'description': 'Use case description'},
                'starting_url': {'type': 'string', 'description': 'URL to navigate to before step 1'},
                'active': {'type': 'boolean'},
                'executing_region': {'type': 'string', 'description': 'AWS region for execution'},
                'tags': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': 'Optional tags for categorization',
                },
            },
            'required': ['name', 'description', 'starting_url', 'active', 'executing_region', 'tags'],
            'additionalProperties': False,
        },
        'steps': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'sort': {
                        'type': 'integer',
                        'description': 'Sequential step number starting from 1',
                    },
                    'instruction': {
                        'type': 'string',
                        'description': 'What the step should do or check',
                    },
                    'step_type': {
                        'type': 'string',
                        'enum': ['navigation', 'validation', 'secret', 'retrieve_value', 'assertion', 'url', 'download', 'network_assertion'],
                        'description': 'Type of test step',
                    },
                    'secret_key': {
                        'type': 'string',
                        'description': 'Secret key name for secret steps, empty string otherwise',
                    },
                    'capture_variable': {
                        'type': 'string',
                        'description': 'Variable name to capture for retrieve_value steps, empty string otherwise',
                    },
                    'validation_type': {
                        'type': 'string',
                        'enum': ['string', 'bool', 'number', ''],
                        'description': 'Data type for validation/assertion comparison, empty string if not applicable',
                    },
                    'validation_operator': {
                        'type': 'string',
                        'enum': [
                            'exact', 'exact_case_insensitive', 'contains',
                            'contains_case_insensitive', 'not_equal',
                            'equals', 'less_then', 'greater_then',
                            'greater_or_equal_then', 'less_or_equal_then', '',
                        ],
                        'description': 'Comparison operator for validation/assertion, empty string if not applicable',
                    },
                    'validation_value': {
                        'type': 'string',
                        'description': 'Expected value for validation/assertion, empty string if not applicable',
                    },
                    'assertion_variable': {
                        'type': 'string',
                        'description': 'Name of a previously captured runtime variable for assertion steps, empty string otherwise',
                    },
                    'value_step': {
                        'type': 'string',
                        'description': 'Reserved field, always empty string',
                    },
                    'value_type': {
                        'type': 'string',
                        'enum': ['string', 'number', 'bool', ''],
                        'description': 'Data type for retrieve_value steps, empty string otherwise',
                    },
                    # network_assertion step fields — optional; only populated
                    # when step_type == 'network_assertion'.
                    'network_url_pattern': {
                        'type': 'string',
                        'description': 'Playwright glob URL pattern (e.g. **/api/users) for network_assertion steps.',
                    },
                    'network_method': {
                        'type': 'string',
                        'enum': ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS', ''],
                        'description': 'Expected HTTP method for network_assertion steps. Empty string means no method check.',
                    },
                    'network_request_body': {
                        'type': 'string',
                        'description': 'Expected request body as JSON string for network_assertion steps. Empty if no body check.',
                    },
                    'network_body_match_type': {
                        'type': 'string',
                        'enum': ['exact', 'subset', 'schema', ''],
                        'description': (
                            'How to match the expected body against the captured request body. '
                            '"schema" treats network_request_body as a JSON Schema Draft 2020-12 '
                            'document; external $ref (http/https/file) is rejected.'
                        ),
                    },
                    'network_mock_response': {
                        'type': 'string',
                        'description': 'Optional mock response as JSON string with shape {status, body, headers}.',
                    },
                    'network_mock_passthrough': {
                        'type': 'boolean',
                        'description': 'If true, fetch the real response and merge with network_mock_response overrides.',
                    },
                    'network_timeout': {
                        'type': 'integer',
                        'description': 'Timeout in seconds (1-120) for waiting on the matching request. Default 15.',
                    },
                    # Response-side assertion fields — all optional.
                    'network_response_body': {
                        'type': 'string',
                        'description': (
                            'Optional expected response body as JSON string. '
                            'Interpreted per network_response_body_match_type (subset or schema). '
                            'Empty string means no response body check.'
                        ),
                    },
                    'network_response_body_match_type': {
                        'type': 'string',
                        'enum': ['subset', 'schema', ''],
                        'description': (
                            'How to match the expected response body against the captured response. '
                            '"exact" is NOT permitted on the response side — response payloads commonly '
                            'contain non-deterministic values (timestamps, generated ids). '
                            'Defaults to "subset" when network_response_body is set without an explicit type.'
                        ),
                    },
                    'network_response_status': {
                        'type': 'integer',
                        'description': (
                            'Optional expected HTTP status code (100-599). Exact match only; '
                            'omit to skip the status check.'
                        ),
                    },
                },
                'required': [
                    'sort', 'instruction', 'step_type', 'secret_key',
                    'capture_variable', 'validation_type', 'validation_operator',
                    'validation_value', 'assertion_variable', 'value_step', 'value_type',
                ],
                'additionalProperties': False,
            },
            'description': 'Ordered list of test steps',
        },
        'variables': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'key': {'type': 'string', 'description': 'Variable name'},
                    'value': {'type': 'string', 'description': 'Default value'},
                },
                'required': ['key', 'value'],
                'additionalProperties': False,
            },
            'description': 'Static user-defined variables (NOT runtime variables from retrieve_value)',
        },
        'secrets': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'key': {'type': 'string', 'description': 'Secret key name'},
                    'description': {'type': 'string', 'description': 'What this secret is for'},
                },
                'required': ['key', 'description'],
                'additionalProperties': False,
            },
            'description': 'Secret references used by secret steps',
        },
        'hooks': {
            'type': 'null',
            'description': 'Always null for generated use cases',
        },
    },
    'required': ['exportVersion', 'exportedAt', 'usecase', 'steps', 'variables', 'secrets', 'hooks'],
    'additionalProperties': False,
}


def _get_tool_config():
    """Build the Bedrock Converse API toolConfig for structured JSON output.

    Uses tool use with toolChoice forced to a specific tool so that
    constrained decoding guarantees the model response conforms to
    USECASE_EXPORT_SCHEMA. This approach works across all models that
    support tool use (Nova Pro, Claude Sonnet, etc.).

    Returns:
        Dict suitable for the toolConfig parameter of bedrock_runtime.converse().
    """
    return {
        'tools': [
            {
                'toolSpec': {
                    'name': 'usecase_export',
                    'description': 'Generate a structured test automation use case export. '
                                   'Populate all fields according to the schema.',
                    'inputSchema': {
                        'json': USECASE_EXPORT_SCHEMA,
                    },
                },
            },
        ],
        'toolChoice': {
            'tool': {
                'name': 'usecase_export',
            },
        },
    }


def _format_action_line(i, action):
    """Format a single recorded action as a prompt line with variable annotations.

    For extract_variable actions, appends the captured variable name and selected text.
    For paste actions linked to a prior extract, appends the source variable reference.

    Args:
        i: 1-based action index.
        action: ActionEntry model instance.

    Returns:
        Formatted string for this action.
    """
    line = f'{i}. [{action.type}] {action.prompt}'
    if action.type == 'extract_variable' and action.variableName:
        line += f' [captures → {{{{{action.variableName}}}}}'
        if action.selectedText:
            line += f', value: "{action.selectedText}"'
        line += ']'
    elif action.type == 'paste' and action.sourceVariableName:
        line += f' [uses → {{{{{action.sourceVariableName}}}}}]'
    if action.url:
        line += f' (URL: {action.url})'
    return line


def _build_variable_instructions(actions):
    """Build variable mapping instructions if the recording contains extract/paste pairs.

    Scans the action list for extract_variable and paste actions. When found,
    produces explicit instructions telling Bedrock how to map them to UseCase
    step types (retrieve_value, navigation with {{Variable}} syntax).

    Args:
        actions: List of ActionEntry model instances.

    Returns:
        A string with variable mapping instructions, or empty string if no
        variable actions are present.
    """
    extracts = [a for a in actions if a.type == 'extract_variable' and a.variableName]
    pastes = [a for a in actions if a.type == 'paste' and a.sourceVariableName]
    if not extracts and not pastes:
        return ''

    lines = [
        '',
        'VARIABLE MAPPING INSTRUCTIONS:',
        'The recording contains variable extraction and/or insertion actions. '
        'Map them to UseCase step types as follows:',
    ]
    if extracts:
        lines.append(
            '- Each "extract_variable" action MUST become a "retrieve_value" step. '
            'Set capture_variable to the variable name shown in [captures → {{name}}]. '
            'Set value_type based on the extracted value (use "string" if uncertain). '
            'The instruction should describe what value to extract from the page.'
        )
    if pastes:
        lines.append(
            '- Each "paste" action with [uses → {{name}}] indicates the user wants to '
            'use a previously captured variable at that point. Generate a single navigation '
            'step that references the variable using {{VariableName}} syntax in the instruction. '
            'Write the step as a goal-oriented instruction describing WHAT to achieve, not HOW '
            'to click through the UI. Examples:\n'
            '  • Date picker: "select {{var_1}} in the \'Date of Birth\' date picker"\n'
            '  • Dropdown: "select {{var_1}} from the \'Country\' dropdown"\n'
            '  • Text field: "type {{var_1}} into the search field"\n'
            'The executing AI model knows how to operate complex widgets — describe the goal, '
            'not the individual clicks.'
        )
    if extracts:
        lines.append(
            '- Every captured variable must be used in at least one later step — either in '
            'an assertion step that compares it, or in a navigation step via {{VariableName}} syntax.'
        )
    lines.append(
        '- Do NOT add captured variables to the "variables" array. '
        'The "variables" array is for user-defined static key-value pairs only. '
        'Variables captured by retrieve_value steps are runtime variables resolved during execution.'
    )
    lines.append(
        '- Beyond the explicitly recorded extract/paste actions, you MAY also generate '
        'additional retrieve_value steps if you identify values in the journey that would '
        'benefit from capture and reuse (e.g., a generated ID, a computed total, or a value '
        'that needs to be verified after a state change). Use your judgment.'
    )
    return '\n'.join(lines)


def _build_recording_section(recording_data):
    """Build the recording context section for the Bedrock prompt.
    
    Extracts the action sequence from validated RecordingData and formats it
    as a structured section to append to the prompt. Includes variable annotations
    for extract_variable and paste actions, plus explicit mapping instructions.
    
    Args:
        recording_data: Validated RecordingData instance with type "cdp_actions".
        
    Returns:
        A string containing the formatted recording section, or empty string
        if the recording data cannot be processed.
    """
    try:
        payload = CDPRecordingPayload(**recording_data.data)
        actions = payload.session.actions
        if not actions:
            return ''
        
        lines = [
            '',
            'RECORDED BROWSER INTERACTION SEQUENCE:',
            'The following actions were recorded during a live browser session. '
            'Use them as supplementary context to produce more accurate and detailed test steps.',
            ''
        ]
        for i, action in enumerate(actions, 1):
            lines.append(_format_action_line(i, action))
        
        lines.append('')
        lines.append(
            'Use the recorded interactions above alongside the user journey description '
            'to generate comprehensive test steps. The recording provides the exact sequence '
            'of user actions — incorporate them into the test case where they align with the journey description.'
        )

        variable_instructions = _build_variable_instructions(actions)
        if variable_instructions:
            lines.append(variable_instructions)

        section = '\n'.join(lines)
        logger.info(f'Built recording section: {len(actions)} actions, {len(section)} chars')
        return section
    except Exception as e:
        logger.warning(f'Failed to build recording section from recording data: {e}')
        return ''


def _select_key_screenshots(actions, manifest, max_screenshots=80):
    """Select the most informative screenshots from the recording.

    Selection priority:
      1. First action (initial page state)
      2. Last action (final state)
      3. First action on each unique URL (page transitions)
      4. Navigation and tab_switch actions (context switches)
      5. Actions with assertions attached
      6. Remaining slots filled evenly spaced across the timeline

    Args:
        actions: List of ActionEntry model instances.
        manifest: Dict of {actionId: s3Key} from the screenshot manifest.
        max_screenshots: Maximum number of screenshots to select.

    Returns:
        List of (action_index, action_id) tuples for selected screenshots.
    """
    if not actions or not manifest:
        return []

    # Only consider actions that have screenshots in the manifest
    available = [(i, a) for i, a in enumerate(actions) if a.id in manifest]
    if not available:
        return []

    selected_set = set()  # set of action indices

    def add(idx):
        if idx not in selected_set and any(i == idx for i, _ in available):
            selected_set.add(idx)

    # 1. First and last
    add(available[0][0])
    add(available[-1][0])

    # 2. First action on each unique URL
    seen_urls = set()
    for i, action in available:
        if action.url and action.url not in seen_urls:
            seen_urls.add(action.url)
            add(i)

    # 3. Navigation and tab_switch actions
    for i, action in available:
        if action.type in ('navigation', 'tab_switch'):
            add(i)

    # 4. Actions with assertions
    for i, action in available:
        if action.assertions:
            add(i)

    # 5. Fill remaining slots evenly spaced
    if len(selected_set) < max_screenshots:
        remaining_slots = max_screenshots - len(selected_set)
        unselected = [(i, a) for i, a in available if i not in selected_set]
        if unselected and remaining_slots > 0:
            step = max(1, len(unselected) // remaining_slots)
            for j in range(0, len(unselected), step):
                if len(selected_set) >= max_screenshots:
                    break
                add(unselected[j][0])

    # Return sorted by action index
    result = []
    for i, action in available:
        if i in selected_set:
            result.append((i, action.id))
    selected = result[:max_screenshots]
    logger.info(
        f'Screenshot selection: {len(selected)}/{len(available)} available '
        f'(from {len(actions)} total actions, {len(manifest)} in manifest)'
    )
    return selected


def _fetch_and_compress_screenshots(s3_client, bucket, manifest, selected_ids, target_width=800):
    """Fetch selected screenshots from S3 and compress them.

    Args:
        s3_client: Boto3 S3 client.
        bucket: S3 bucket name.
        manifest: Dict of {actionId: s3Key}.
        selected_ids: List of (action_index, action_id) tuples.
        target_width: Target width for downscaling (maintains aspect ratio).

    Returns:
        Dict of {action_id: compressed_image_bytes}.
    """
    try:
        from PIL import Image
    except ImportError:
        logger.warning('Pillow not available, skipping screenshot compression')
        return {}

    def fetch_one(action_index, action_id):
        try:
            s3_key = manifest[action_id]
            obj = s3_client.get_object(Bucket=bucket, Key=s3_key)
            raw_bytes = obj['Body'].read()

            img = Image.open(io.BytesIO(raw_bytes))
            if img.width > target_width:
                ratio = target_width / img.width
                new_height = int(img.height * ratio)
                img = img.resize((target_width, new_height), Image.LANCZOS)

            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=70)
            return action_id, buf.getvalue()
        except Exception as e:
            logger.warning(f'Failed to fetch/compress screenshot {action_id}: {e}')
            return action_id, None

    results = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_one, idx, aid) for idx, aid in selected_ids]
        for future in futures:
            action_id, data = future.result()
            if data:
                results[action_id] = data

    total_bytes = sum(len(v) for v in results.values())
    logger.info(
        f'Compressed {len(results)}/{len(selected_ids)} screenshots, '
        f'total payload: {total_bytes / 1024:.0f} KB'
    )
    return results


def _build_recording_content_blocks(recording_data, screenshots=None):
    """Build interleaved text + image content blocks for the recording section.

    Includes variable annotations for extract_variable and paste actions,
    plus explicit mapping instructions when variable actions are present.

    Args:
        recording_data: Validated RecordingData instance.
        screenshots: Dict of {action_id: image_bytes} for selected screenshots.

    Returns:
        List of Bedrock content blocks (text and image dicts), or empty list.
    """
    screenshots = screenshots or {}
    try:
        payload = CDPRecordingPayload(**recording_data.data)
        actions = payload.session.actions
    except Exception as e:
        logger.warning(f'Failed to parse recording data for content blocks: {e}')
        return []

    if not actions:
        return []

    blocks = []
    blocks.append({'text': (
        'RECORDED BROWSER INTERACTION SEQUENCE:\n'
        'The following actions were recorded during a live browser session. '
        'Where a screenshot is attached, it shows the browser state at that action.\n'
    )})

    for i, action in enumerate(actions, 1):
        blocks.append({'text': _format_action_line(i, action)})

        # Interleave screenshot immediately after its action
        if action.id in screenshots:
            blocks.append({
                'image': {
                    'format': 'jpeg',
                    'source': {'bytes': screenshots[action.id]}
                }
            })

    closing = (
        'Use the recorded interactions and their screenshots to generate '
        'comprehensive test steps. The screenshots show the actual browser state '
        'at each action — use them to identify specific UI elements and page layout.'
    )
    variable_instructions = _build_variable_instructions(actions)
    if variable_instructions:
        closing += '\n' + variable_instructions

    blocks.append({'text': closing})
    return blocks



def create_prompt(title, starting_url, user_journey, region, recording_data=None):
    """Create the prompt for Amazon Bedrock based on the user journey.

    Args:
        title: Use case title.
        starting_url: Starting URL for the test.
        user_journey: User journey description text. Can be empty when recording_data is provided.
        region: AWS region for execution.
        recording_data: Optional validated RecordingData instance. When present,
            the prompt is augmented with the recorded interaction sequence.

    Returns:
        The complete prompt string for Bedrock.
    """
    current_time = get_current_timestamp()

    # Escape quotes for JSON safety
    escaped_title = title.replace('"', '\\"')
    escaped_journey = user_journey.replace('"', '\\"') if user_journey else ''

    # Build the journey description section — adapt when only recording is provided
    if user_journey.strip():
        journey_detail = f'- Journey Description: {user_journey}'
        description_text = f'Generated from user journey: {escaped_journey}'
    elif recording_data is not None:
        journey_detail = '- Journey Description: (derived from browser recording below)'
        description_text = f'Generated from browser recording for {escaped_title}'
    else:
        journey_detail = '- Journey Description: '
        description_text = f'Generated from user journey: {escaped_journey}'

    prompt = f'''You are an expert test automation engineer. Convert the following user journey description into a structured JSON format for automated web testing.

DESIGN PRINCIPLES:
- SIMPLICITY FIRST: Prefer the fewest steps possible. Each step should do exactly one thing. Shorter test cases are better — do not add steps that are not strictly necessary to cover the user journey.
- STEP TYPE PRIORITY: Prefer "validation" over "retrieve_value" + "assertion". Only use retrieve_value/assertion when a value must be captured and compared after a state change or reused across multiple later steps.
- CLEAR TRANSITIONS: Each navigation step must describe exactly one user-level action with an unambiguous target element. Moving between steps should be logical and precise.
- SEMANTIC OVER MECHANICAL: When a user interacts with a complex UI widget (date picker, dropdown, autocomplete, multi-step selector), generate ONE navigation step that describes the goal (e.g., "select {{DOB}} in the 'Date of Birth' date picker") rather than multiple micro-steps for each click within the widget. The executing AI model understands how to operate these widgets — your job is to describe WHAT to achieve, not HOW to click through the widget.

User Journey Details:
- Title: (Wizard) {title}
- Starting URL: {starting_url}
{journey_detail}

Your response MUST conform to the JSON schema enforced by the system. The output is imported into a test automation system.

Use these exact values for the top-level fields:
- exportVersion: "1.0"
- exportedAt: "{current_time}"
- usecase.name: "{escaped_title}"
- usecase.description: "{description_text}"
- usecase.starting_url: "{starting_url}"
- usecase.active: true
- usecase.executing_region: "{region}"
- usecase.tags: []
- secrets: []
- hooks: null

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
10. Validation step instruction must start with "return the value of ...". like: "return the value of the product count on the page". The instruction must ask for the actual content (text, number, etc.) — NEVER ask whether something "is visible" or "exists" because the executing model will return true/false instead of the actual value.
11. Retrieve value step instruction must describe what value to extract from the page. Set capture_variable to the variable name and value_type to "string", "number", or "bool".
12. Assertion steps do NOT interact with the browser. Set assertion_variable to the name of a previously captured runtime variable, and set validation_type, validation_operator, and validation_value for the comparison.
13. URL step instruction must be ONLY the raw URL (e.g. "https://example.com/page") — do NOT include any natural language prefix like "navigate to". The instruction field is passed directly to the browser's navigation API, so any text other than the URL will cause an error.
14. Each step MUST have ALL fields present, use empty strings ("") for unused fields
15. Sort steps sequentially starting from 1 (no gaps or duplicates)
16. All strings must be properly escaped for JSON
17. Do not generate a URL step or navigation step to the starting_url. The system automatically navigates to the starting_url before step 1. Do not duplicate this.
18. Secret steps must focus an input field only.
19. Instructions must be written as instructions. Like "click the search button" or "Return the amount of items in the basket"
20. The FIRST step of every use case MUST be a validation step that confirms the page has fully loaded by reading a key element's text content (e.g. the main heading text or page title). This ensures all subsequent steps operate on a stable, fully rendered page.
21. Every retrieve_value step should be followed by at least one assertion step that references the captured variable. Do not generate a retrieve_value step without a corresponding assertion that uses it. If the value only needs to be checked once and not compared after a state change, use a validation step instead.

Step Type Guidelines:
- "navigation": For clicking buttons, filling forms, navigating pages. Each step should describe exactly one user-level interaction. For complex widgets (date pickers, dropdowns, autocomplete fields), write a single goal-oriented step (e.g., "select 03/15/2026 in the 'Date of Birth' date picker") instead of multiple micro-steps for each click within the widget.
- "validation": PREFERRED for any check. For checking page content, verifying elements exist. Reads a value from the live page and compares it. Use this instead of retrieve_value + assertion whenever possible. The instruction MUST ask for the actual content (e.g. "return the value of the heading text"), NEVER ask about visibility or existence (the executing model would return true/false instead of the content).
- "secret": For using stored credentials (set secret_key field). Secrets are managed by users outside this generation — NEVER populate the top-level "secrets" array. Only reference existing secret keys in step secret_key fields when the journey explicitly mentions credentials.
- "retrieve_value": ONLY use when the value must be stored for later comparison after a state change or reused in multiple assertion steps. Do NOT use just to read and immediately check a value — use validation instead.
- "assertion": ONLY use to compare a previously captured runtime variable. Requires a preceding retrieve_value step. Do NOT use as a substitute for validation.
- "url": For navigating directly to a specific URL. The instruction MUST be the raw URL only (e.g. "https://example.com/page") with NO natural language text — it is passed directly to the browser navigation API. Do not use to navigate to the starting_url.
- "download": For downloading a file from the page

DO / DON'T Examples:

DON'T: retrieve_value to capture a button label, then assertion to check it equals "Submit"
DO: Use a single validation step: "return the value of the submit button label" with validation_type "string" and validation_value "Submit"

DON'T: Use a URL step to navigate to the starting_url as the first step
DO: Start with a validation step confirming the page has loaded, e.g. "return the value of the main page heading" with validation_type "string", validation_operator "contains", and validation_value set to the expected heading text

DON'T: Write validation instructions that ask about visibility or existence (e.g. "return the value for the heading being visible") — the executing model will return true/false instead of the actual content
DO: Write validation instructions that ask for the actual content (e.g. "return the value of the page heading text")

DON'T: Split a single check into retrieve_value + assertion when the value is only needed once
DO: Use validation to check the value directly on the page

DON'T: Generate multiple micro-steps for a complex widget (e.g., "click the month dropdown", "select March", "click day 15", "click year field", "type 2026")
DO: Generate one goal-oriented step: "select {{DOB}} in the 'Date of Birth' date picker" — the executing AI model knows how to operate the widget

DO: Use retrieve_value + assertion when you need to capture a count before an action, perform the action, then capture and compare the count after
DO: Use retrieve_value when the same value needs to be referenced in multiple later assertion steps

Variables:
- There are TWO kinds of variables in this system. Do not confuse them:
  1. STATIC VARIABLES: User-defined key-value pairs in the "variables" array. Referenced via {{{{VariableName}}}} and resolved before step execution. Use these for reusable inputs (search terms, category names, etc.) that appear in multiple steps or that a user might want to change between runs.
  2. RUNTIME VARIABLES: Captured by "retrieve_value" steps during execution. Also referenced via {{{{VariableName}}}} in later steps. These are NOT added to the "variables" array — they exist only at runtime.
- Use the built-in {{{{UniqueID}}}} variable when creating resources that need unique names to avoid collisions across test runs (e.g., "[QA Test] {{{{UniqueID}}}}").
- Do NOT create static variables for strings that only appear once and are not a parameterizable key element. Static values like button labels, menu item names, or fixed URLs should be hardcoded directly in the instruction.
- Other built-in variables available without definition: {{{{Time}}}}, {{{{ExecutionID}}}}, {{{{CreatedAt}}}}.
- You MAY generate retrieve_value steps proactively when you identify values in the journey that benefit from capture and reuse — for example, a generated ID, a computed total, or a value that needs to be verified after a state change. This applies whether or not a browser recording is present.

Generate the complete, valid JSON now:'''

    logger.info(
        f'Prompt built: title="{title[:80]}", starting_url="{starting_url}", '
        f'journey_len={len(user_journey)} chars, region={region}, '
        f'has_recording={recording_data is not None}'
    )

    # Augment prompt with recording data when present
    if recording_data is not None:
        recording_section = _build_recording_section(recording_data)
        if recording_section:
            prompt += recording_section

    return prompt



def _is_nova2_model(model_id):
    """Check if the model ID is an Amazon Nova 2 model that supports extended thinking."""
    return 'nova-2' in model_id.lower()


def invoke_bedrock(title, starting_url, user_journey, region, model_id, recording_data=None, screenshots=None):
    """Make a single call to Amazon Bedrock using the Converse API with tool-based structured output.

    Uses toolConfig with toolChoice forced to 'usecase_export' so that
    constrained decoding guarantees the model response conforms to
    USECASE_EXPORT_SCHEMA. This approach works across all models that
    support tool use (Nova 2 Lite, Claude Sonnet, Qwen, etc.).

    For Nova 2 models, extended thinking is enabled with low reasoning effort
    via additionalModelRequestFields.

    When screenshots are provided, the recording section is sent as interleaved
    text + image content blocks instead of a single text block. This allows the
    model to see the browser state at each action.
    """
    start_time = time.time()

    if screenshots and recording_data:
        # Build prompt WITHOUT recording section (we'll interleave it with images)
        prompt = create_prompt(title, starting_url, user_journey, region, recording_data=None)
        content_blocks = [{'text': prompt}]
        recording_blocks = _build_recording_content_blocks(recording_data, screenshots)
        content_blocks.extend(recording_blocks)
        image_count = sum(1 for b in content_blocks if 'image' in b)
        text_block_count = sum(1 for b in content_blocks if 'text' in b)
        logger.info(
            f'Multi-modal Bedrock call: {len(content_blocks)} content blocks '
            f'({text_block_count} text, {image_count} images)'
        )
        logger.info(f'Recording section interleaved with {image_count} screenshots')
    else:
        # Text-only path (no screenshots available)
        prompt = create_prompt(title, starting_url, user_journey, region, recording_data=recording_data)
        content_blocks = [{'text': prompt}]
        has_recording = recording_data is not None and 'RECORDED BROWSER INTERACTION' in prompt
        logger.info(
            f'Text-only Bedrock call '
            f'(recording section {"included" if has_recording else "NOT included"}, '
            f'no screenshots)'
        )

    tool_config = _get_tool_config()
    logger.info('Structured output enabled: toolConfig with forced toolChoice (usecase_export)')

    # Build converse kwargs — Nova 2 with low reasoning allows inferenceConfig
    use_extended_thinking = _is_nova2_model(model_id)
    converse_kwargs = {
        'modelId': model_id,
        'messages': [{
            'role': 'user',
            'content': content_blocks,
        }],
        'toolConfig': tool_config,
    }

    if use_extended_thinking:
        # Nova 2 low effort: allows inferenceConfig with maxTokens
        converse_kwargs['inferenceConfig'] = {
            'maxTokens': 40000,
            'temperature': 0,
        }
        converse_kwargs['additionalModelRequestFields'] = {
            'reasoningConfig': {
                'type': 'enabled',
                'maxReasoningEffort': 'low',
            }
        }
        logger.info('Extended thinking enabled: Nova 2 model with low reasoning effort')
    else:
        converse_kwargs['inferenceConfig'] = {
            'maxTokens': 8192,
            'temperature': 0.1,
        }

    print(f'Invoking Amazon Bedrock model {model_id} with {len(content_blocks)} content blocks '
          f'(tool-based structured output, extended_thinking={use_extended_thinking})')

    try:
        response = bedrock_runtime.converse(**converse_kwargs)

        duration = time.time() - start_time
        print(f'Amazon Bedrock model invocation completed in {duration:.2f}s')

        # Extract the generated content — skip reasoningContent blocks (Nova 2 extended thinking)
        content = response['output']['message']['content']
        if not content:
            raise Exception('Invalid response format from Amazon Bedrock: no content')

        # Find the toolUse block in the response (skip reasoningContent blocks)
        tool_use_block = None
        for block in content:
            if 'reasoningContent' in block:
                logger.info('Skipping reasoningContent block (extended thinking)')
                continue
            if 'toolUse' in block:
                tool_use_block = block['toolUse']
                break

        if tool_use_block is None:
            # Fallback: try text block (shouldn't happen with forced toolChoice)
            text_blocks = [b for b in content if 'text' in b]
            generated_text = text_blocks[0].get('text', '') if text_blocks else ''
            if not generated_text:
                raise Exception('Invalid response format from Amazon Bedrock: no toolUse or text block')
            generated_json = extract_json(generated_text)
        else:
            # Tool use response: input is already a dict conforming to the schema
            generated_json = json.dumps(tool_use_block['input'])

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
    - userJourney: Description of the user journey (optional if recording_data is provided)
    - region: AWS region for execution (required)
    - recording_data: Optional RecordingData object with browser recording context
    
    At least one of userJourney or recording_data must be provided.
    
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
    
    # Parse and validate optional recording_data
    recording_data = None
    raw_recording_data = body.get('recording_data')
    if raw_recording_data is not None:
        try:
            recording_data = RecordingData(**raw_recording_data)
            try:
                action_count = len(CDPRecordingPayload(**recording_data.data).session.actions)
            except Exception:
                action_count = '?'
            logger.info(
                f'[{request_id}] Valid recording_data received '
                f'(type={recording_data.type}, actions={action_count})'
            )
        except Exception as e:
            logger.warning(f'[{request_id}] Malformed recording_data, ignoring: {e}')
            recording_data = None
    
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
    
    # Validate user journey — optional when recording_data is present
    has_user_journey = bool(user_journey.strip())
    if has_user_journey:
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
    elif not recording_data:
        # No user journey and no recording — at least one is required
        validation_errors.append({
            'field': 'userJourney',
            'message': 'User journey description is required when no recording data is provided',
            'code': 'REQUIRED'
        })
    
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
        # Load screenshots from S3 if available
        screenshots = None
        if recording_data and recording_data.screenshot_manifest_key:
            try:
                s3 = boto3.client('s3')
                bucket = os.environ.get('BUCKET_NAME')
                if bucket:
                    manifest_obj = s3.get_object(Bucket=bucket, Key=recording_data.screenshot_manifest_key)
                    manifest = json.loads(manifest_obj['Body'].read())
                    actions = CDPRecordingPayload(**recording_data.data).session.actions
                    selected = _select_key_screenshots(actions, manifest)
                    screenshots = _fetch_and_compress_screenshots(s3, bucket, manifest, selected)
                    logger.info(f'[{request_id}] Loaded {len(screenshots)} screenshots for Bedrock')
            except Exception as e:
                logger.warning(f'[{request_id}] Failed to load screenshots, proceeding without: {e}')
                screenshots = None

        print(f'[INFO] [{request_id}] Calling Amazon Bedrock service to generate usecase')
        generated_json = invoke_bedrock(title, starting_url, user_journey, region, model_id, recording_data=recording_data, screenshots=screenshots)
        
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
