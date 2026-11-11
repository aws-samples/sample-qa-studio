"""
AWS Lambda function for executing test suites.

This endpoint creates a suite execution record and execution records for ALL
use cases in the suite, applies overrides (base_url, variables, region, model_id).
For OnDemand trigger_type, it invokes the execute_usecase Lambda to spawn ECS tasks.
For ci_runner trigger_type, it creates execution records only (no ECS tasks).

Endpoint: POST /api/test-suites/{id}/execute
"""
import lambda_init  # noqa: F401 — must be first import (execution_steps → dataset_ref → dataset_models uses pydantic)
import json
import os
import time
import boto3
from typing import Dict, Any, Iterable, List, Optional
from urllib.parse import urlparse
from botocore.exceptions import ClientError

# Import from local modules in endpoints directory
from utils import (
    create_response,
    get_table_name,
    get_current_timestamp,
    generate_uuid7,
    extract_user_identity,
    validate_path_id)
from resource_auth import require_resource_access, suite_from_path
from test_suite_schema import (
    get_test_suites_pk,
    get_suite_sk,
    get_suite_mapping_pk
)
from platforms import ELECTRON_CI_RUNNER_ONLY_ERROR, electron_trigger_allowed
from url_override import apply_base_url_override
from variable_merge import (
    client_item_reader,
    load_application_variables,
    load_usecase_variables,
    merge_layers,
    merge_variables,
    rows_to_dict,
    validate_variables_resolved,
)
from execution_steps import (
    DatasetNotFoundError,
    RepeatExpansionError,
    build_execution_step_items,
    write_execution_step_items,
)
from dataset_ref import UNRESOLVED_DATASET_ERROR, DatasetFetcher, application_dataset_fetcher

dynamodb = boto3.client('dynamodb')
eventbridge = boto3.client('events')
cloudwatch = boto3.client('cloudwatch')
lambda_client = boto3.client('lambda')


def log_event(event_type: str, data: Dict[str, Any]) -> None:
    """
    Log structured event to CloudWatch Logs.
    
    Args:
        event_type: Type of event (e.g., 'suite_execution_started')
        data: Event data dictionary
    """
    log_entry = {
        'timestamp': get_current_timestamp(),
        'event_type': event_type,
        'data': data
    }
    print(json.dumps(log_entry))

def resolve_triggered_by(user_identity: Dict[str, Any], table_name: str) -> str:
    """
    Resolve the triggered_by display value.
    For user tokens, returns the email. For M2M tokens, looks up the OAuth
    client name from DynamoDB so the execution record shows a human-readable name
    instead of the raw client_id.
    """
    if user_identity.get('identity_type') != 'client':
        return user_identity['identity']

    client_id = user_identity['identity']
    try:
        response = dynamodb.get_item(
            TableName=table_name,
            Key={
                'pk': {'S': 'OAUTH_CLIENTS'},
                'sk': {'S': client_id}
            },
            ProjectionExpression='client_name'
        )
        item = response.get('Item')
        if item and 'client_name' in item:
            client_name = item['client_name']['S']
            print(f"Resolved client_id {client_id} to client_name '{client_name}'")
            return client_name
    except Exception as e:
        print(f"Failed to resolve client name for {client_id}: {str(e)}")

    # Fallback to client_id if lookup fails
    return client_id




def publish_metrics(suite_execution_id: str, execution_count: int, duration_ms: float, has_overrides: Dict[str, bool]) -> None:
    """
    Publish custom CloudWatch metrics.
    
    Args:
        suite_execution_id: Suite execution UUID
        execution_count: Number of executions created
        duration_ms: Duration in milliseconds
        has_overrides: Dict indicating which overrides were applied
    """
    try:
        metric_data = [
            {
                'MetricName': 'SuiteExecutionCreated',
                'Value': 1,
                'Unit': 'Count',
                'Dimensions': [
                    {'Name': 'TriggerType', 'Value': 'ci_runner'}
                ]
            },
            {
                'MetricName': 'UsecaseExecutionsCreated',
                'Value': execution_count,
                'Unit': 'Count'
            },
            {
                'MetricName': 'ExecutionCreationDuration',
                'Value': duration_ms,
                'Unit': 'Milliseconds'
            }
        ]
        
        # Add override metrics
        if has_overrides.get('base_url'):
            metric_data.append({
                'MetricName': 'BaseUrlOverridesApplied',
                'Value': 1,
                'Unit': 'Count'
            })
        
        if has_overrides.get('variables'):
            metric_data.append({
                'MetricName': 'VariableOverridesApplied',
                'Value': 1,
                'Unit': 'Count'
            })
        
        cloudwatch.put_metric_data(
            Namespace='NovaActQA/SuiteExecution',
            MetricData=metric_data
        )
        print(f'Published CloudWatch metrics for suite execution {suite_execution_id}')
    except Exception as e:
        print(f'Error publishing CloudWatch metrics: {str(e)}')
        # Don't fail the request if metrics publishing fails


def get_test_suite(suite_id: str, table_name: str) -> Dict[str, Any]:
    """
    Fetch test suite definition from DynamoDB.
    
    Args:
        suite_id: Test suite UUID
        table_name: DynamoDB table name
    
    Returns:
        Suite definition dictionary
    
    Raises:
        ValueError: If suite not found
    """
    response = dynamodb.get_item(
        TableName=table_name,
        Key={
            'pk': {'S': get_test_suites_pk()},
            'sk': {'S': get_suite_sk(suite_id)}
        }
    )
    
    if 'Item' not in response:
        raise ValueError(f'Test suite not found: {suite_id}')
    
    item = response['Item']
    return {
        'id': item.get('id', {}).get('S', ''),
        'name': item.get('name', {}).get('S', ''),
        'description': item.get('description', {}).get('S', ''),
        'scope': item.get('scope', {}).get('S', ''),
        'total_usecases': int(item.get('total_usecases', {}).get('N', '0'))
    }


def get_suite_usecases(suite_id: str, table_name: str) -> List[Dict[str, Any]]:
    """
    Fetch all usecase mappings for a test suite.
    
    Args:
        suite_id: Test suite UUID
        table_name: DynamoDB table name
    
    Returns:
        List of usecase mappings with usecase_id and usecase_name
    """
    response = dynamodb.query(
        TableName=table_name,
        KeyConditionExpression='pk = :pk AND begins_with(sk, :prefix)',
        ExpressionAttributeValues={
            ':pk': {'S': get_suite_mapping_pk(suite_id)},
            ':prefix': {'S': 'USECASE#'}
        }
    )
    
    usecases = []
    for item in response.get('Items', []):
        usecases.append({
            'usecase_id': item.get('usecase_id', {}).get('S', ''),
            'usecase_name': item.get('usecase_name', {}).get('S', '')
        })
    
    return usecases


def get_usecase_definition(usecase_id: str, table_name: str) -> Dict[str, Any]:
    """
    Fetch usecase definition from DynamoDB.
    
    Args:
        usecase_id: Usecase UUID
        table_name: DynamoDB table name
    
    Returns:
        Usecase definition dictionary
    
    Raises:
        ValueError: If usecase not found
    """
    response = dynamodb.get_item(
        TableName=table_name,
        Key={
            'pk': {'S': 'USECASES'},
            'sk': {'S': f'USECASE#{usecase_id}'}
        }
    )
    
    if 'Item' not in response:
        raise ValueError(f'Usecase not found: {usecase_id}')
    
    item = response['Item']
    return {
        'id': usecase_id,
        'name': item.get('name', {}).get('S', ''),
        'starting_url': item.get('starting_url', {}).get('S', ''),
        'executing_region': item.get('executing_region', {}).get('S', ''),
        'model_id': item.get('model_id', {}).get('S', ''),
        'enable_cache': item.get('enable_cache', {}).get('BOOL', False),
        'test_platform': item.get('test_platform', {}).get('S', 'web'),
        'platform': item.get('platform', {}).get('S', ''),
        'app_package': item.get('app_package', {}).get('S', ''),
        'app_activity': item.get('app_activity', {}).get('S', ''),
        'bundle_id': item.get('bundle_id', {}).get('S', ''),
        'app_binary_s3_path': item.get('app_binary_s3_path', {}).get('S', ''),
        'app_arn': item.get('app_arn', {}).get('S', ''),
        'device_farm_project_arn': item.get('device_farm_project_arn', {}).get('S', ''),
        'device_arn': item.get('device_arn', {}).get('S', ''),
        'browser_policy_s3_path': item.get('browser_policy_s3_path', {}).get('S', ''),
        'application_id': item.get('application_id', {}).get('S', ''),
    }


def get_application_variables(application_ids: Iterable[str], table_name: str) -> Dict[str, Dict[str, str]]:
    """
    Prefetch the application variable layer, one ``get_item`` per distinct
    application (not per use case).

    Returns:
        ``{application_id: {key: value}}``; applications without a
        ``VARIABLES`` record map to ``{}``. Empty ids are skipped.
    """
    read_item = client_item_reader(dynamodb, table_name)
    return {
        application_id: load_application_variables(read_item, application_id)
        for application_id in sorted({app_id for app_id in application_ids if app_id})
    }


def get_usecase_variables(usecase_id: str, table_name: str, app_vars: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Effective variables of a use case: the (prefetched) application layer
    under the use case's own ``USECASE_VARIABLES`` record.

    Args:
        usecase_id: Usecase UUID
        table_name: DynamoDB table name
        app_vars: The use case's application layer from
            ``get_application_variables`` (``None`` / ``{}`` = no application)

    Returns:
        ``{key: value}``; the use case wins per key. Secret values are never
        part of it (H-1).
    """
    usecase_vars = load_usecase_variables(client_item_reader(dynamodb, table_name), usecase_id)
    return rows_to_dict(merge_layers(app_vars or {}, usecase_vars))


def get_dataset_fetchers(application_ids: Iterable[str], table_name: str) -> Dict[str, DatasetFetcher]:
    """
    One memoising dataset fetcher per distinct application (``''`` included,
    for use cases without an application — it resolves nothing).  Sharing
    the fetcher across the use cases of an application and across the dry
    run and the real build means one ``get_item`` per referenced dataset for
    the whole suite; nothing is read for use cases without a reference.

    Returns:
        ``{application_id: fetch(dataset_id) -> dataset record | None}``
    """
    read_item = client_item_reader(dynamodb, table_name)
    return {
        application_id: application_dataset_fetcher(read_item, application_id or None)
        for application_id in set(application_ids)
    }


def create_suite_execution_record(
    suite_id: str,
    suite_execution_id: str,
    suite_name: str,
    suite_scope: str,
    triggered_by: str,
    trigger_type: str,
    overrides: Dict[str, Any],
    total_usecases: int,
    created_at: str,
    table_name: str
) -> Dict[str, Any]:
    """
    Create suite execution record in DynamoDB.
    
    Args:
        suite_id: Test suite UUID
        suite_execution_id: Suite execution UUID (UUIDv7)
        suite_name: Name of the test suite
        suite_scope: Scope of the test suite (e.g., 'suite:smoke-tests')
        triggered_by: Identity of the user/client who triggered the execution
        trigger_type: Trigger type ('ci_runner', 'manual', or 'scheduled')
        overrides: Dictionary of overrides (base_url, variables, region, model_id)
        total_usecases: Total number of usecases in the suite
        created_at: ISO8601 timestamp
        table_name: DynamoDB table name
    
    Returns:
        Created suite execution record
    """
    # Build the item according to design spec (matches create_suite_execution_item schema)
    item = {
        'pk': {'S': f'SUITE_EXECUTION#{suite_id}'},
        'sk': {'S': f'EXECUTION#{suite_execution_id}'},
        'id': {'S': suite_execution_id},
        'suite_id': {'S': suite_id},
        'suite_name': {'S': suite_name},
        'suite_scope': {'S': suite_scope},
        'status': {'S': 'pending'},
        'started_at': {'S': created_at},
        'triggered_by': {'S': triggered_by},
        'trigger_type': {'S': trigger_type},
        'created_at': {'S': created_at},
        'total_usecases': {'N': str(total_usecases)},
        'completed_usecases': {'N': '0'},
        'successful_usecases': {'N': '0'},
        'failed_usecases': {'N': '0'},
        'running_usecases': {'N': str(total_usecases)}
    }
    
    # Add overrides as a map
    overrides_map = {}
    if overrides.get('base_url'):
        overrides_map['base_url'] = {'S': overrides['base_url']}
    if overrides.get('variables'):
        # Convert variables dict to DynamoDB map
        vars_map = {}
        for key, value in overrides['variables'].items():
            vars_map[key] = {'S': str(value)}
        overrides_map['variables'] = {'M': vars_map}
    if overrides.get('region'):
        overrides_map['region'] = {'S': overrides['region']}
    if overrides.get('model_id'):
        overrides_map['model_id'] = {'S': overrides['model_id']}
    
    if overrides_map:
        item['overrides'] = {'M': overrides_map}
    
    # Create the record
    dynamodb.put_item(
        TableName=table_name,
        Item=item
    )
    
    print(f'Created suite execution record: {suite_execution_id}')
    
    return {
        'suite_execution_id': suite_execution_id,
        'suite_id': suite_id,
        'status': 'pending',
        'created_at': created_at
    }


def update_suite_execution_with_executions(
    suite_execution_id: str,
    suite_id: str,
    execution_ids: List[Dict[str, str]],
    table_name: str
) -> None:
    """
    Update suite execution record with list of usecase executions.
    
    Args:
        suite_execution_id: Suite execution UUID
        suite_id: Test suite UUID
        execution_ids: List of dicts with usecase_id, execution_id, usecase_name
        table_name: DynamoDB table name
    """
    # Convert execution_ids to DynamoDB list format
    executions_list = []
    for exec_info in execution_ids:
        executions_list.append({
            'M': {
                'usecase_id': {'S': exec_info['usecase_id']},
                'execution_id': {'S': exec_info['execution_id']},
                'usecase_name': {'S': exec_info['usecase_name']},
                'status': {'S': 'pending'}
            }
        })
    
    dynamodb.update_item(
        TableName=table_name,
        Key={
            'pk': {'S': f'SUITE_EXECUTION#{suite_id}'},
            'sk': {'S': f'EXECUTION#{suite_execution_id}'}
        },
        UpdateExpression='SET usecase_executions = :executions',
        ExpressionAttributeValues={
            ':executions': {'L': executions_list}
        }
    )
    
    print(f'Updated suite execution {suite_execution_id} with {len(execution_ids)} executions')


def get_usecase_steps(usecase_id: str, table_name: str) -> List[Dict[str, Any]]:
    """Fetch the STEP# records of a usecase (low-level typed format)."""
    steps_result = dynamodb.query(
        TableName=table_name,
        KeyConditionExpression='pk = :pk AND begins_with(sk, :prefix)',
        ExpressionAttributeValues={
            ':pk': {'S': f'USECASE#{usecase_id}'},
            ':prefix': {'S': 'STEP#'}
        }
    )
    return steps_result.get('Items', [])


def create_execution_record_for_usecase(
    usecase_id: str,
    usecase_definition: Dict[str, Any],
    suite_execution_id: str,
    suite_id: str,
    trigger_type: str,
    starting_url: str,
    variables: Dict[str, str],
    region: str,
    model_id: str,
    created_at: str,
    table_name: str,
    steps: Optional[List[Dict[str, Any]]] = None,
    dataset_fetcher: Optional[DatasetFetcher] = None,
) -> str:
    """
    Create execution record for a single usecase.
    
    Reuses logic from execute_usecase Lambda:
    - Creates execution record
    - Copies steps
    - Copies hooks
    - Copies variables (merged)
    - Copies headers
    
    Args:
        usecase_id: Usecase UUID
        usecase_definition: Usecase definition dict
        suite_execution_id: Suite execution UUID
        suite_id: Test suite UUID
        trigger_type: Trigger type ('ci_runner', 'manual', or 'scheduled')
        starting_url: Starting URL (with base_url override applied)
        variables: Merged variables dictionary
        region: Execution region (with override applied)
        model_id: Model ID (with override applied)
        created_at: ISO8601 timestamp
        table_name: DynamoDB table name
        steps: Prefetched STEP# records (typed format); queried when omitted
        dataset_fetcher: Resolves ``dataset_id`` repeat steps against the use
            case's application (``get_dataset_fetchers``); without one a
            reference raises ``DatasetNotFoundError``
    
    Returns:
        execution_id (UUIDv7)
    """
    # Generate execution ID (UUIDv7 for time-ordered sorting)
    execution_id = generate_uuid7()

    # Resolve dataset references and unroll repeats before writing anything
    # so a bad dataset cannot leave a half-created execution (the handler
    # pre-validates, this is the belt-and-braces path).
    if steps is None:
        steps = get_usecase_steps(usecase_id, table_name)
    execution_step_items = build_execution_step_items(
        steps, execution_id, created_at, dataset_fetcher=dataset_fetcher,
    )
    
    # Create execution record
    execution_item = {
        'pk': {'S': f'USECASE_EXECUTION#{usecase_id}'},
        'sk': {'S': f'EXECUTION#{execution_id}'},
        'starting_url': {'S': starting_url},
        'status': {'S': 'pending'},
        'created_at': {'S': created_at},
        'trigger_type': {'S': trigger_type},
        'executing_region': {'S': region},
        'model_id': {'S': model_id},
        'suite_execution_id': {'S': suite_execution_id},
        'suite_id': {'S': suite_id},
        'usecase_name': {'S': usecase_definition.get('name', '')}
    }
    
    # Propagate enable_cache from usecase to execution record
    if usecase_definition.get('enable_cache', False):
        execution_item['enable_cache'] = {'BOOL': True}

    # Copy browser policy path if configured
    browser_policy_s3_path = usecase_definition.get('browser_policy_s3_path', '')
    if browser_policy_s3_path:
        execution_item['browser_policy_s3_path'] = {'S': browser_policy_s3_path}
    
    # Copy mobile config fields from usecase to execution record
    test_platform = usecase_definition.get('test_platform', 'web')
    execution_item['test_platform'] = {'S': test_platform}

    if test_platform == 'mobile':
        platform_val = usecase_definition.get('platform', '')
        if platform_val:
            execution_item['platform'] = {'S': platform_val}

        # Build app_identifier
        app_package = usecase_definition.get('app_package', '')
        app_activity = usecase_definition.get('app_activity', '')
        bundle_id = usecase_definition.get('bundle_id', '')
        if platform_val == 'ANDROID' and app_package and app_activity:
            execution_item['app_identifier'] = {'S': f'{app_package}/{app_activity}'}
        elif platform_val == 'IOS' and bundle_id:
            execution_item['app_identifier'] = {'S': bundle_id}

        # Copy optional mobile fields if present
        for field in ['app_binary_s3_path', 'app_arn', 'device_farm_project_arn', 'device_arn']:
            val = usecase_definition.get(field, '')
            if val:
                execution_item[field] = {'S': val}
    elif test_platform == 'electron':
        # Optional bundle id the runner verifies against the launched .app
        if usecase_definition.get('bundle_id'):
            execution_item['bundle_id'] = {'S': usecase_definition['bundle_id']}
    
    dynamodb.put_item(
        TableName=table_name,
        Item=execution_item
    )
    print(f'Created execution {execution_id} for usecase {usecase_id}')
    
    # Create execution step records (shared builder, batched writes)
    write_execution_step_items(dynamodb, table_name, execution_step_items)
    
    print(f'Created {len(execution_step_items)} execution steps for execution {execution_id}')
    
    # Load and copy hooks
    try:
        hooks_result = dynamodb.get_item(
            TableName=table_name,
            Key={
                'pk': {'S': f'USECASE#{usecase_id}'},
                'sk': {'S': 'HOOKS'}
            }
        )
        
        if 'Item' in hooks_result:
            hooks = hooks_result['Item']
            execution_hooks = {
                'pk': {'S': f'EXECUTION#{execution_id}'},
                'sk': {'S': 'HOOKS'},
                'created_at': {'S': created_at}
            }
            
            if 'before_script' in hooks:
                execution_hooks['before_script'] = hooks['before_script']
            if 'after_script' in hooks:
                execution_hooks['after_script'] = hooks['after_script']
            
            dynamodb.put_item(TableName=table_name, Item=execution_hooks)
            print(f'Copied hooks to execution {execution_id}')
    except Exception as e:
        print(f'Error copying hooks: {str(e)}')
    
    # Store merged variables as EXECUTION_VARIABLES
    if variables:
        variables_map = {}
        for key, value in variables.items():
            variables_map[key] = {'S': str(value)}
        
        execution_variables = {
            'pk': {'S': f'EXECUTION#{execution_id}'},
            'sk': {'S': 'EXECUTION_VARIABLES'},
            'created_at': {'S': created_at},
            'variables': {'M': variables_map}
        }
        
        dynamodb.put_item(TableName=table_name, Item=execution_variables)
        print(f'Copied {len(variables)} variables to execution {execution_id}')
    
    # Load and copy headers
    try:
        headers_result = dynamodb.get_item(
            TableName=table_name,
            Key={
                'pk': {'S': f'USECASE#{usecase_id}'},
                'sk': {'S': 'HEADERS'}
            }
        )
        
        if 'Item' in headers_result:
            headers = headers_result['Item']
            execution_headers = {
                'pk': {'S': f'EXECUTION#{execution_id}'},
                'sk': {'S': 'HEADERS'},
                'created_at': {'S': created_at}
            }
            
            if 'headers' in headers:
                execution_headers['headers'] = headers['headers']
            
            dynamodb.put_item(TableName=table_name, Item=execution_headers)
            print(f'Copied headers to execution {execution_id}')
    except Exception as e:
        print(f'Error copying headers: {str(e)}')
    
    return execution_id


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Entry point. EventBridge (suite schedules) invokes directly without a
    requestContext; those calls are authorized by the IAM permission on this
    Lambda. API calls need api/suite.write + api/executions.write and execute
    on the suite's application (each use case is re-checked by execute_usecase).
    """
    if not event.get('requestContext'):
        scheduler_identity = {'identity': 'scheduler', 'identity_type': 'scheduler', 'sub': '', 'scopes': []}
        return _execute_suite(event, scheduler_identity)
    return _authorized_handler(event, context)


@require_resource_access('execute', suite_from_path, scopes=['api/suite.write', 'api/executions.write'])
def _authorized_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    return _execute_suite(event, extract_user_identity(event))


def _execute_suite(event: Dict[str, Any], user_identity: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a test suite by creating suite execution and all usecase execution records.
    
    This endpoint creates execution records with overrides applied,
    without spawning ECS tasks (trigger_type=ci_runner/OnDemand).
    
    Path Parameters:
        id: Test suite UUID
    
    Request Body:
        trigger_type: One of "ci_runner", "OnDemand"
        base_url: Optional base URL override for all usecases
        variables: Optional variable overrides (key-value pairs)
        region: Optional AWS region override
        model_id: Optional Amazon Bedrock model ID override
    
    Returns:
        200: Suite execution created with all execution IDs
        400: Invalid request (missing variables, invalid base_url, etc.)
        403: Insufficient permissions
        404: Test suite not found
        500: Internal server error
    """
    print(f"Suite execution requested by identity type: {user_identity['identity_type']}")

    # Parse path parameters
    suite_id, error = validate_path_id(event.get('pathParameters', {}).get('suite_id'), 'suite ID')
    if error:
        return error
    
    # Parse request body
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return create_response(400, {'error': 'Invalid JSON in request body'})
    
    # Validate trigger_type
    trigger_type = body.get('trigger_type', 'OnDemand')
    valid_trigger_types = ['ci_runner', 'OnDemand', 'scheduled']
    if trigger_type not in valid_trigger_types:
        return create_response(400, {
            'error': 'Invalid trigger type',
            'message': f'trigger_type must be one of: {", ".join(valid_trigger_types)}'
        })
    
    # Extract overrides
    base_url = body.get('base_url')
    cli_variables = body.get('variables', {})
    region_override = body.get('region')
    model_id_override = body.get('model_id')
    
    # Validate base_url format if provided
    if base_url:
        try:
            parsed = urlparse(base_url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError('Invalid URL format')
            if parsed.scheme not in ['http', 'https']:
                raise ValueError('Scheme must be http or https')
        except Exception as e:
            return create_response(400, {
                'error': 'Invalid base URL',
                'message': f'Base URL must be a valid URL with scheme and domain: {str(e)}'
            })
    
    # Validate variables is a dictionary
    if not isinstance(cli_variables, dict):
        return create_response(400, {
            'error': 'Invalid variables',
            'message': 'variables must be a dictionary of key-value pairs'
        })

    # Dataset overrides are a single-usecase feature (qa-studio run
    # --dataset-file); refuse explicitly instead of silently ignoring them.
    if 'repeat_datasets' in body:
        return create_response(400, {
            'error': 'repeat_datasets is not supported for suites',
            'message': 'Dataset overrides are only accepted on POST /usecase/{id}/execute',
        })
    
    print(f'Executing suite: {suite_id}, trigger_type: {trigger_type}')
    print(f'Overrides - base_url: {base_url}, variables: {bool(cli_variables)}, region: {region_override}, model_id: {model_id_override}')
    
    table_name = get_table_name()
    created_at = get_current_timestamp()
    start_time = __import__('time').time()
    
    # Log suite execution started
    log_event('suite_execution_started', {
        'suite_id': suite_id,
        'trigger_type': trigger_type,
        'overrides': {
            'base_url': bool(base_url),
            'variables': bool(cli_variables),
            'region': bool(region_override),
            'model_id': bool(model_id_override)
        },
        'requested_by': user_identity['identity']
    })
    
    try:
        # 1. Fetch test suite definition
        try:
            suite = get_test_suite(suite_id, table_name)
        except ValueError as e:
            return create_response(404, {
                'error': 'Test suite not found',
                'message': str(e)
            })
        
        print(f'Fetched suite: {suite["name"]} with {suite["total_usecases"]} usecases')
        
        # 2. Fetch all usecase mappings
        usecases = get_suite_usecases(suite_id, table_name)
        
        if not usecases:
            return create_response(400, {
                'error': 'Empty test suite',
                'message': 'Test suite contains no usecases'
            })
        
        print(f'Fetched {len(usecases)} usecase mappings')

        # 2b. Fetch every usecase definition up front. Two reasons: the
        # electron gate below must run before *any* record is written (a
        # half-created suite execution is worse than a clean 400), and a
        # usecase missing from the table is a data-integrity error we want
        # to report before creating the suite execution, not mid-loop.
        usecase_definitions: Dict[str, Dict[str, Any]] = {}
        for usecase_mapping in usecases:
            mapping_usecase_id = usecase_mapping['usecase_id']
            try:
                usecase_definitions[mapping_usecase_id] = get_usecase_definition(
                    mapping_usecase_id, table_name,
                )
            except ValueError:
                print(f'ERROR: Usecase {mapping_usecase_id} not found but is in suite {suite_id}')
                return create_response(500, {
                    'error': 'Data integrity error',
                    'message': f'Usecase {mapping_usecase_id} referenced by suite but not found'
                })

        # Electron usecases run only on the CI runner's host; the cloud
        # worker (which OnDemand/scheduled suites spawn) cannot launch them.
        electron_blocked = [
            uid for uid, definition in usecase_definitions.items()
            if not electron_trigger_allowed(definition.get('test_platform', 'web'), trigger_type)
        ]
        if electron_blocked:
            return create_response(400, {
                'error': ELECTRON_CI_RUNNER_ONLY_ERROR,
                'details': {'usecase_ids': electron_blocked},
            })

        # 2c. Prefetch the application variable layer once per application
        # (inherited by every use case of that application; the use case's
        # own record is read per use case below and wins per key).
        application_variables = get_application_variables(
            (definition.get('application_id', '') for definition in usecase_definitions.values()),
            table_name,
        )

        # 2d. Prefetch steps, resolve dataset references and dry-run the
        # repeat expansion for every usecase.  A dataset missing from the use
        # case's application, or a repeat that cannot be unrolled (no rows,
        # no children, orphan child), fails the whole request with 400 before
        # the suite execution record exists, instead of leaving half-written
        # records.  Fetchers are shared per application (one read per dataset).
        dataset_fetchers = get_dataset_fetchers(
            (definition.get('application_id', '') for definition in usecase_definitions.values()),
            table_name,
        )
        usecase_steps: Dict[str, List[Dict[str, Any]]] = {}
        for mapping_usecase_id, definition in usecase_definitions.items():
            usecase_steps[mapping_usecase_id] = get_usecase_steps(mapping_usecase_id, table_name)
            try:
                build_execution_step_items(
                    usecase_steps[mapping_usecase_id], 'dry-run', created_at,
                    dataset_fetcher=dataset_fetchers[definition.get('application_id', '')],
                )
            except DatasetNotFoundError as e:
                return create_response(400, {
                    'error': UNRESOLVED_DATASET_ERROR,
                    'dataset_id': e.dataset_id,
                    'details': {'usecase_id': mapping_usecase_id},
                })
            except RepeatExpansionError as e:
                return create_response(400, {
                    'error': 'Invalid repeat step',
                    'message': str(e),
                    'details': {'usecase_id': mapping_usecase_id},
                })
        
        # 3. Create suite execution record
        suite_execution_id = generate_uuid7()
        
        overrides = {}
        if base_url:
            overrides['base_url'] = base_url
        if cli_variables:
            overrides['variables'] = cli_variables
        if region_override:
            overrides['region'] = region_override
        if model_id_override:
            overrides['model_id'] = model_id_override
        
        triggered_by = resolve_triggered_by(user_identity, table_name)
        
        create_suite_execution_record(
            suite_id=suite_id,
            suite_execution_id=suite_execution_id,
            suite_name=suite['name'],
            suite_scope=suite['scope'],
            triggered_by=triggered_by,
            trigger_type=trigger_type,
            overrides=overrides,
            total_usecases=len(usecases),
            created_at=created_at,
            table_name=table_name
        )
        
        print(f'Created suite execution: {suite_execution_id}')
        
        # 4. Loop through all usecases and create execution records
        execution_ids = []
        
        # Get execute_usecase Lambda ARN for OnDemand/scheduled invocations
        execute_usecase_arn = os.environ.get('EXECUTE_USECASE_LAMBDA_ARN') if trigger_type in ('OnDemand', 'scheduled') else None
        
        for usecase_mapping in usecases:
            usecase_id = usecase_mapping['usecase_id']
            usecase_name = usecase_mapping['usecase_name']
            
            try:
                # Definition was prefetched above (step 2b)
                usecase = usecase_definitions[usecase_id]
                
                # Effective variables: application layer (prefetched in 2c)
                # under the use case's own record. Secret values are never
                # merged into execution variables (readable by Viewers via
                # GET .../executions/{id}/variables); the runner reads them
                # per step from Secrets Manager with execute access (H-1).
                usecase_vars = get_usecase_variables(
                    usecase_id, table_name, application_variables.get(usecase.get('application_id', ''))
                )
                
                # Apply base URL override
                modified_starting_url = apply_base_url_override(
                    usecase['starting_url'],
                    base_url
                )
                
                # Merge variables with precedence: CLI > usecase
                merged_vars = merge_variables({}, usecase_vars, cli_variables)
                
                # Validate all variables resolved
                validate_variables_resolved(usecase, merged_vars)
                
                # Determine region and model_id (override or default)
                execution_region = region_override if region_override else (
                    usecase['executing_region'] if usecase['executing_region'] else 
                    os.environ.get('DEFAULT_REGION', 'us-east-1')
                )
                execution_model_id = model_id_override if model_id_override else usecase['model_id']
                
                if trigger_type in ('OnDemand', 'scheduled') and execute_usecase_arn:
                    invoke_payload = {
                        'pathParameters': {'id': usecase_id},
                        'queryStringParameters': {
                            'trigger-type': 'OnDemandHeadless',
                            'suite-execution-id': suite_execution_id,
                            'suite-id': suite_id,
                        },
                        'requestContext': event.get('requestContext', {}),
                    }

                    max_retries = 3
                    execution_id = ''
                    invocation_succeeded = False

                    for attempt in range(max_retries):
                        try:
                            response = lambda_client.invoke(
                                FunctionName=execute_usecase_arn,
                                InvocationType='RequestResponse',
                                Payload=json.dumps(invoke_payload),
                            )

                            status_code = response.get('StatusCode', 0)
                            if status_code == 429:
                                wait = 2 ** attempt
                                print(f'Throttled invoking execute_usecase for {usecase_id}, retry {attempt + 1}/{max_retries} in {wait}s')
                                time.sleep(wait)
                                continue

                            resp_payload = json.loads(response['Payload'].read().decode('utf-8'))
                            resp_body = json.loads(resp_payload.get('body', '{}'))
                            execution_id = resp_body.get('executionId', '')

                            if resp_payload.get('statusCode', 0) >= 400:
                                print(f'WARNING: execute_usecase returned error for {usecase_id}: {resp_body}')
                                break

                            invocation_succeeded = True
                            break

                        except ClientError as e:
                            error_code = e.response['Error']['Code']
                            if error_code in ('TooManyRequestsException', 'ServiceException'):
                                wait = 2 ** attempt
                                print(f'ClientError {error_code} invoking execute_usecase for {usecase_id}, retry {attempt + 1}/{max_retries} in {wait}s')
                                time.sleep(wait)
                            else:
                                print(f'ERROR: Unretryable error invoking execute_usecase for {usecase_id}: {e}')
                                break

                    if not invocation_succeeded:
                        print(f'WARNING: execute_usecase invocation failed for {usecase_id} after {max_retries} attempts')
                        continue
                else:
                    # ci_runner: create execution record only, no ECS task
                    execution_id = create_execution_record_for_usecase(
                        usecase_id=usecase_id,
                        usecase_definition=usecase,
                        suite_execution_id=suite_execution_id,
                        suite_id=suite_id,
                        trigger_type=trigger_type,
                        starting_url=modified_starting_url,
                        variables=merged_vars,
                        region=execution_region,
                        model_id=execution_model_id,
                        created_at=created_at,
                        table_name=table_name,
                        steps=usecase_steps.get(usecase_id),
                        dataset_fetcher=dataset_fetchers[usecase.get('application_id', '')],
                    )
                
                execution_ids.append({
                    'usecase_id': usecase_id,
                    'execution_id': execution_id,
                    'usecase_name': usecase_name
                })
                
                print(f'Created execution {execution_id} for usecase {usecase_name}')
                
            except ValueError as e:
                # Variable validation failed (usecase-not-found is caught in step 2b)
                error_msg = str(e)
                if 'Unresolved variables' in error_msg:
                    return create_response(400, {
                        'error': 'Unresolved variables',
                        'message': error_msg,
                        'details': {
                            'usecase_id': usecase_id,
                            'usecase_name': usecase_name
                        }
                    })
                else:
                    print(f'ERROR: Unexpected validation error for usecase {usecase_id}: {error_msg}')
                    return create_response(500, {
                        'error': 'Data integrity error',
                        'message': error_msg
                    })
        
        # 5. Update suite execution with all execution IDs
        update_suite_execution_with_executions(
            suite_execution_id=suite_execution_id,
            suite_id=suite_id,
            execution_ids=execution_ids,
            table_name=table_name
        )
        
        # 6. Publish Amazon EventBridge event
        try:
            eventbridge.put_events(
                Entries=[{
                    'Source': 'nova-act-qa-studio.suite-execution',
                    'DetailType': 'nova-act-qa-studio.suite-execution.created',
                    'Detail': json.dumps({
                        'suite_id': suite_id,
                        'suite_execution_id': suite_execution_id,
                        'trigger_type': trigger_type,
                        'usecase_count': len(execution_ids),
                        'timestamp': created_at
                    }),
                    'EventBusName': 'default'
                }]
            )
            print(f'Published suite execution created event')
        except Exception as e:
            print(f'Error publishing Amazon EventBridge event: {str(e)}')
            # Don't fail the request if event publishing fails
        
        # 7. Publish CloudWatch metrics
        duration_ms = (__import__('time').time() - start_time) * 1000
        publish_metrics(
            suite_execution_id=suite_execution_id,
            execution_count=len(execution_ids),
            duration_ms=duration_ms,
            has_overrides={
                'base_url': bool(base_url),
                'variables': bool(cli_variables),
                'region': bool(region_override),
                'model_id': bool(model_id_override)
            }
        )
        
        # Log completion
        log_event('suite_execution_completed', {
            'suite_execution_id': suite_execution_id,
            'suite_id': suite_id,
            'execution_count': len(execution_ids),
            'duration_ms': duration_ms
        })
        
        # 8. Return response
        return create_response(200, {
            'suite_execution_id': suite_execution_id,
            'suite_id': suite_id,
            'status': 'pending',
            'created_at': created_at,
            'execution_ids': execution_ids
        })
        
    except Exception as e:
        print(f'Error executing test suite: {str(e)}')
        import traceback
        traceback.print_exc()
        return create_response(500, {
            'error': 'Failed to execute test suite',
            'message': str(e)
        })

