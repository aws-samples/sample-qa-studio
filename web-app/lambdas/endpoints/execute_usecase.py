import lambda_init  # noqa: F401 — must be first import (execution_steps → dataset_ref → dataset_models uses pydantic)
import hashlib
import json
import os
import secrets
import boto3
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import BotoCoreError, ClientError
from utils import create_response, get_table_name, get_current_timestamp, generate_uuid7, allow_m2m_token, validate_path_id
from platforms import ELECTRON_CI_RUNNER_ONLY_ERROR, electron_trigger_allowed
from execution_steps import (
    DatasetNotFoundError,
    RepeatExpansionError,
    build_execution_step_items,
    write_execution_step_items,
)
from dataset_ref import UNRESOLVED_DATASET_ERROR, application_dataset_fetcher
from repeat_validation import validate_dataset
from resource_auth import require_resource_access, usecase_from_path
from variable_merge import client_item_reader, load_effective_usecase_variables
import microvm_launch
import running_executions
from run_payload import MobileConfig, RunPayload

dynamodb = boto3.client('dynamodb')
eventbridge = boto3.client('events')


def update_execution_microvm_info(usecase_id, execution_id, microvm_id, cloudwatch_url):
    """Update the execution record with the worker MicroVM metadata."""
    try:
        dynamodb.update_item(
            TableName=get_table_name(),
            Key={
                'pk': {'S': f'USECASE_EXECUTION#{usecase_id}'},
                'sk': {'S': f'EXECUTION#{execution_id}'}
            },
            UpdateExpression='SET microvm_id = :microvm_id, cloudwatch_logs_url = :cloudwatch_url',
            ExpressionAttributeValues={
                ':microvm_id': {'S': microvm_id},
                ':cloudwatch_url': {'S': cloudwatch_url}
            }
        )
        print(f'Updated execution {execution_id} with MicroVM ID: {microvm_id}')
    except Exception as e:
        print(f'Error updating execution MicroVM info: {str(e)}')
        raise


def mobile_config_from_usecase(usecase) -> MobileConfig:
    """Mobile fields for the RunPayload: the use-case attributes the worker
    exports as upper-cased env vars (``MobileConfig.to_env``), non-empty only."""
    fields = {
        'test_platform': 'mobile',
        'platform': usecase.get('platform', {}).get('S', ''),
        'app_package': usecase.get('app_package', {}).get('S', ''),
        'app_activity': usecase.get('app_activity', {}).get('S', ''),
        'bundle_id': usecase.get('bundle_id', {}).get('S', ''),
        'app_binary_s3_path': usecase.get('app_binary_s3_path', {}).get('S', ''),
        'app_arn': usecase.get('app_arn', {}).get('S', ''),
        'device_farm_project_arn': usecase.get('device_farm_project_arn', {}).get('S', ''),
        'device_arn': usecase.get('device_arn', {}).get('S', ''),
    }
    return MobileConfig(**{name: value for name, value in fields.items() if value})


def record_running_execution(usecase_id, execution_id, microvm_id, max_duration_s, suite_execution_id=None):
    """Write the RUNNING_EXECUTIONS tracking record for a launched VM.

    Best-effort: the VM is already running and the execution record carries
    its id, so a failure here is logged and must not fail the launch — the
    reconciler only loses this execution from its query until it finishes.
    """
    record = running_executions.new_running_execution(
        execution_id=execution_id,
        usecase_id=usecase_id,
        microvm_id=microvm_id,
        mode='batch',
        max_duration_s=max_duration_s,
        suite_execution_id=suite_execution_id,
    )
    try:
        running_executions.put_running_execution(dynamodb, get_table_name(), record)
        print(f'Recorded running execution {execution_id} (deadline {record.deadline})')
    except (ClientError, BotoCoreError) as e:
        print(f'Error recording running execution {execution_id}: {str(e)}')


def start_microvm_execution(usecase_id, execution_id, usecase, test_platform, worker_token,
                            execution_region, s3_bucket, suite_execution_id=None):
    """Launch the worker MicroVM for a cloud execution and record its identifiers.

    Per-execution values travel in the run-hook payload (``RunPayload``); stack
    constants are image-level env. The VM runs in the stack region
    (``AWS_REGION``); ``execution_region`` only selects the artefact bucket.
    Any failure (after the throttling retries, an oversized payload, a model
    error) marks the execution ``failed`` and returns 500.
    After a successful launch the RUNNING_EXECUTIONS tracking record is written
    (best-effort) so the reconciler can find the execution without a scan.
    """
    try:
        max_duration_s = int(os.environ['MAX_EXECUTION_DURATION_MINUTES']) * 60
        log_group = os.environ['MICROVM_LOG_GROUP']
        payload = RunPayload(
            mode='batch',
            usecase_id=usecase_id,
            execution_id=execution_id,
            execution_token=worker_token,
            region=execution_region,
            s3_bucket=s3_bucket,
            user_agent=os.environ.get('USER_AGENT') or None,
            max_duration_s=max_duration_s,
            mobile=mobile_config_from_usecase(usecase) if test_platform == 'mobile' else None,
        )
        result = microvm_launch.launch_microvm(
            microvm_launch.get_microvm_client(),
            image_arn=os.environ['MICROVM_IMAGE_ARN'],
            image_version=os.environ['MICROVM_IMAGE_VERSION'],
            execution_role_arn=os.environ['MICROVM_EXECUTION_ROLE_ARN'],
            log_group=log_group,
            log_stream=execution_id,
            payload=payload,
            max_duration_s=max_duration_s,
            client_token=execution_id,
        )
        microvm_id = result['microvmId']
        print(f'MicroVM started - ID: {microvm_id}, state: {result.get("state")}')

        cloudwatch_url = microvm_launch.microvm_cloudwatch_logs_url(os.environ['AWS_REGION'], log_group, execution_id)
        print(f'CloudWatch Logs URL: {cloudwatch_url}')

        update_execution_microvm_info(usecase_id, execution_id, microvm_id, cloudwatch_url)
        record_running_execution(usecase_id, execution_id, microvm_id, max_duration_s, suite_execution_id)

        return create_response(200, {
            'status': 'microvm started',
            'usecaseId': usecase_id,
            'executionId': execution_id,
            'microvmId': microvm_id,
            'cloudWatchLogsUrl': cloudwatch_url
        })
    except Exception as e:
        error_msg = f'Failed to start MicroVM: {str(e)}'
        print(f'Error starting MicroVM: {error_msg}')
        update_execution_status_with_error(usecase_id, execution_id, 'failed', error_msg)
        return create_response(500, {'error': error_msg})

def publish_execution_status_event(usecase_id, execution_id, status):
    """Publish an execution status change event to Amazon EventBridge."""
    try:
        event_detail = {
            'usecase_id': usecase_id,
            'execution_id': execution_id,
            'status': status,
            'timestamp': get_current_timestamp()
        }
        
        eventbridge.put_events(
            Entries=[{
                'Source': 'nova-act-qa-studio.execution',
                'DetailType': 'nova-act-qa-studio.execution.status.changed',
                'Detail': json.dumps(event_detail),
                'EventBusName': 'default'
            }]
        )
        print(f'Published execution status event: {usecase_id}/{execution_id} -> {status}')
    except Exception as e:
        print(f'Error publishing event to Amazon EventBridge: {str(e)}')
        # Don't fail the execution if event publishing fails

def update_execution_status_with_error(usecase_id, execution_id, status, error_msg):
    """Update execution status and log error details."""
    try:
        dynamodb.update_item(
            TableName=get_table_name(),
            Key={
                'pk': {'S': f'USECASE_EXECUTION#{usecase_id}'},
                'sk': {'S': f'EXECUTION#{execution_id}'}
            },
            UpdateExpression='SET #status = :status, completed_at = :completed_at, error_message = :error_msg',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': {'S': status},
                ':completed_at': {'S': get_current_timestamp()},
                ':error_msg': {'S': error_msg}
            }
        )
        print(f'Updated execution {execution_id} status to {status} with error: {error_msg}')
        publish_execution_status_event(usecase_id, execution_id, status)
    except Exception as e:
        print(f'Error updating execution status: {str(e)}')


def parse_repeat_datasets(raw_body):
    """Parse the optional ``repeat_datasets`` execute body.

    Returns ``(overrides_or_None, error_message_or_None)``.  Shape and caps
    are validated with the same rules as stored datasets
    (``repeat_validation.validate_dataset``); label existence and column
    match are checked by the expansion against the actual repeat steps.
    """
    if not raw_body:
        return None, None
    try:
        body = json.loads(raw_body)
    except (json.JSONDecodeError, TypeError):
        return None, 'Invalid JSON in request body'
    if not isinstance(body, dict):
        return None, 'Request body must be a JSON object'
    datasets = body.get('repeat_datasets')
    if datasets is None:
        return None, None
    if not isinstance(datasets, dict):
        return None, 'repeat_datasets must be an object mapping repeat labels to {columns, rows}'
    errors = []
    for label, dataset in datasets.items():
        if not isinstance(dataset, dict):
            errors.append(f'repeat_datasets["{label}"] must be an object with columns and rows')
            continue
        dataset_errors = validate_dataset(dataset.get('columns'), dataset.get('rows'))
        errors.extend(f'repeat_datasets["{label}"]: {e}' for e in dataset_errors)
    if errors:
        return None, '; '.join(errors)
    return datasets, None


def new_worker_token() -> tuple:
    """
    Execution-bound worker capability.

    Returns:
        (token, sha256 hex digest). Only the hash is stored on the execution
        record; the token travels to the worker MicroVM as
        RunPayload.execution_token.
    """
    token = secrets.token_urlsafe(32)
    return token, hashlib.sha256(token.encode()).hexdigest()


def handler(event, context):
    """
    Entry point. EventBridge Scheduler invokes directly (no requestContext);
    those calls are already authorized by the IAM permission on this Lambda.
    Every API call needs api/usecases.execute and execute on the use case's
    application (orphaned use cases are admin-only).
    """
    if not event.get('requestContext'):
        scheduler_identity = {'identity': 'scheduler', 'identity_type': 'scheduler', 'sub': '', 'scopes': []}
        return _execute(event, scheduler_identity)
    return _authorized_handler(event, context)


@require_resource_access('execute', usecase_from_path, scopes=['api/usecases.execute'])
def _authorized_handler(event, context):
    user_identity, error_response = allow_m2m_token(event)
    if error_response:
        return error_response
    return _execute(event, user_identity)


def _execute(event, user_identity):
    """
    Execute a usecase by creating an execution record and launching a worker MicroVM.
    Supports OnDemandHeadless (default), Scheduled and ci_runner trigger types.
    Accessible by both user tokens and M2M tokens.
    
    Path Parameters:
    - id: Usecase ID to execute
    
    Query Parameters:
    - trigger-type: OnDemandHeadless (default), Scheduled, or ci_runner.
      The former use-case-level 'OnDemand' (SQS queue) is rejected with 400:
      no stack ever provisioned its queue.
    
    Request Body (optional JSON):
    - repeat_datasets: {"<repeat label>": {"columns": [...], "rows": [[...]]}}
      Replaces the stored rows of the labelled repeat step for this execution.
      Unknown label, column mismatch, or caps exceeded → 400 before any write.
      Repeat steps referencing an application dataset (dataset_id) are
      resolved first; a dataset missing from the use case's application →
      400 {error: "dataset not found", dataset_id} before any write.
    
    Trigger Types:
    - Scheduled: Launches a worker MicroVM (used by Amazon EventBridge Scheduler)
    - OnDemandHeadless: Launches a worker MicroVM (used by UI for immediate execution)
    - ci_runner: Creates execution record only, no MicroVM (used by CI/CD runner)
    
    Returns:
    - 200: Execution started successfully
    - 400: Missing usecase ID or invalid trigger type
    - 401: Unauthorized
    - 500: Error starting execution
    """
    print(f"Execution requested by identity type: {user_identity['identity_type']}")
    
    usecase_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'usecase ID')

    
    if error:

    
        return error
    
    query_params = event.get('queryStringParameters') or {}
    trigger_type = query_params.get('trigger-type', 'OnDemandHeadless')
    suite_execution_id = query_params.get('suite-execution-id')  # Optional: for suite executions
    suite_id = query_params.get('suite-id')  # Optional: for suite executions
    
    # Validate trigger type
    valid_trigger_types = ['OnDemandHeadless', 'Scheduled', 'ci_runner']
    if trigger_type not in valid_trigger_types:
        return create_response(400, {
            'error': f'Invalid trigger type: {trigger_type}. Valid values: {", ".join(valid_trigger_types)}'
        })
    
    print(f'usecaseID: {usecase_id}, triggertype: {trigger_type}, suite_execution_id: {suite_execution_id}, suite_id: {suite_id}')

    # Optional JSON body: {"repeat_datasets": {"<label>": {"columns": [...], "rows": [[...]]}}}
    # replaces the stored rows of the labelled repeat step for this execution.
    # Never log the body — it carries test data.
    dataset_overrides, body_error = parse_repeat_datasets(event.get('body'))
    if body_error:
        return create_response(400, {'error': body_error})
    
    table_name = get_table_name()
    created_at = get_current_timestamp()
    
    try:
        # Load usecase
        usecase_result = dynamodb.get_item(
            TableName=table_name,
            Key={
                'pk': {'S': 'USECASES'},
                'sk': {'S': f'USECASE#{usecase_id}'}
            }
        )
        
        if 'Item' not in usecase_result:
            return create_response(404, {'error': 'Usecase not found'})
        
        usecase = usecase_result['Item']
        print(usecase)

        starting_url = usecase.get('starting_url', {}).get('S', '')
        test_platform = usecase.get('test_platform', {}).get('S', 'web')
        # Owning application: source of the inherited variable layer and of
        # the datasets repeat steps may reference ('' = orphaned use case).
        application_id = usecase.get('application_id', {}).get('S', '')

        # Electron apps are launched on the CI runner's host; the cloud
        # worker cannot run them. Refuse before any record is written.
        if not electron_trigger_allowed(test_platform, trigger_type):
            return create_response(400, {'error': ELECTRON_CI_RUNNER_ONLY_ERROR})

        # Get executing_region from usecase, use default if empty or missing
        region = usecase.get('executing_region', {}).get('S', '').strip()
        if not region:
            region = os.environ.get('DEFAULT_REGION', 'us-east-1')
        model_id = usecase.get('model_id', {}).get('S', '')
        
        # Generate execution ID (UUIDv7 for time-ordered sorting)
        execution_id = generate_uuid7()
        
        # Create execution record
        execution_item = {
            'pk': {'S': f'USECASE_EXECUTION#{usecase_id}'},
            'sk': {'S': f'EXECUTION#{execution_id}'},
            'starting_url': {'S': starting_url},
            'status': {'S': 'pending'},
            'created_at': {'S': created_at},
            'trigger_type': {'S': trigger_type},
            'executing_region': {'S': region},
            'model_id': {'S': model_id}
        }

        # Cloud runs get an execution-bound worker capability; only its hash
        # is stored (the worker presents the token via X-QA-Execution-Token).
        worker_token = None
        if trigger_type in ('Scheduled', 'OnDemandHeadless'):
            worker_token, worker_token_hash = new_worker_token()
            execution_item['worker_token_hash'] = {'S': worker_token_hash}
        
        # Copy mobile config fields from usecase to execution record
        execution_item['test_platform'] = {'S': test_platform}

        if test_platform == 'mobile':
            # Copy platform (e.g., "ANDROID", "IOS") if present
            usecase_platform = usecase.get('platform', {}).get('S', '')
            if usecase_platform:
                execution_item['platform'] = {'S': usecase_platform}

            # Build app_identifier: Android = "app_package/app_activity", iOS = "bundle_id"
            app_package = usecase.get('app_package', {}).get('S', '')
            app_activity = usecase.get('app_activity', {}).get('S', '')
            bundle_id = usecase.get('bundle_id', {}).get('S', '')
            if usecase_platform == 'ANDROID' and app_package and app_activity:
                execution_item['app_identifier'] = {'S': f'{app_package}/{app_activity}'}
            elif usecase_platform == 'IOS' and bundle_id:
                execution_item['app_identifier'] = {'S': bundle_id}

            # Copy optional mobile fields if present
            for field in ['app_binary_s3_path', 'app_arn', 'device_farm_project_arn', 'device_arn']:
                val = usecase.get(field, {}).get('S', '')
                if val:
                    execution_item[field] = {'S': val}
        elif test_platform == 'electron':
            # Optional: the runner compares it with the launched .app's
            # CFBundleIdentifier so a suite cannot run against the wrong app.
            electron_bundle_id = usecase.get('bundle_id', {}).get('S', '')
            if electron_bundle_id:
                execution_item['bundle_id'] = {'S': electron_bundle_id}

        # Propagate enable_cache from usecase to execution record
        enable_cache_val = usecase.get('enable_cache', {}).get('BOOL', False)
        if enable_cache_val:
            execution_item['enable_cache'] = {'BOOL': True}

        # Copy browser policy path if configured
        browser_policy_s3_path = usecase.get('browser_policy_s3_path', {}).get('S', '')
        if browser_policy_s3_path:
            execution_item['browser_policy_s3_path'] = {'S': browser_policy_s3_path}
        
        # Add suite_execution_id and suite_id if this is part of a suite execution
        if suite_execution_id:
            execution_item['suite_execution_id'] = {'S': suite_execution_id}
            print(f'Execution is part of suite execution: {suite_execution_id}')
        
        if suite_id:
            execution_item['suite_id'] = {'S': suite_id}
            print(f'Execution is part of suite: {suite_id}')

        # Load steps and build the execution steps *before* writing anything:
        # a dataset reference that cannot be resolved or a repeat that cannot
        # be unrolled must fail with 400 and leave no half-written execution
        # behind.  Dataset records are only read for steps that reference one.
        steps_result = dynamodb.query(
            TableName=table_name,
            KeyConditionExpression='pk = :pk AND begins_with(sk, :prefix)',
            ExpressionAttributeValues={
                ':pk': {'S': f'USECASE#{usecase_id}'},
                ':prefix': {'S': 'STEP#'}
            }
        )
        steps = steps_result.get('Items', [])
        dataset_fetcher = application_dataset_fetcher(
            client_item_reader(dynamodb, table_name), application_id or None,
        )
        try:
            execution_step_items = build_execution_step_items(
                steps, execution_id, created_at, dataset_overrides, dataset_fetcher,
            )
        except DatasetNotFoundError as e:
            return create_response(400, {'error': UNRESOLVED_DATASET_ERROR, 'dataset_id': e.dataset_id})
        except RepeatExpansionError as e:
            return create_response(400, {'error': str(e)})
        
        dynamodb.put_item(
            TableName=table_name,
            Item=execution_item
        )
        print(f'Created execution {execution_id}')
        
        # Publish pending status event
        publish_execution_status_event(usecase_id, execution_id, 'pending')
        
        # Create execution step records (shared builder, batched writes)
        write_execution_step_items(dynamodb, table_name, execution_step_items)
        
        print(f'Created {len(execution_step_items)} execution steps')

        
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
                print('Copied hooks to execution')
        except Exception as e:
            print(f'Error copying hooks: {str(e)}')
        
        # Snapshot the effective variables (application layer under the use
        # case layer). The worker reads this record, so inherited rows must
        # be here; ``source`` is not part of the snapshot.
        try:
            effective_variables = load_effective_usecase_variables(
                client_item_reader(dynamodb, table_name), usecase_id, application_id or None,
            )
            if effective_variables:
                execution_variables = {
                    'pk': {'S': f'EXECUTION#{execution_id}'},
                    'sk': {'S': 'EXECUTION_VARIABLES'},
                    'created_at': {'S': created_at},
                    'variables': TypeSerializer().serialize(
                        [{'key': row['key'], 'value': row['value']} for row in effective_variables]
                    ),
                }
                dynamodb.put_item(TableName=table_name, Item=execution_variables)
                print(f'Copied {len(effective_variables)} variables to execution')
        except Exception as e:
            print(f'Error copying variables: {str(e)}')
        
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
                print('Copied headers to execution')
        except Exception as e:
            print(f'Error copying headers: {str(e)}')
        
        # Mobile pre-validation: require app binary reference before execution
        if test_platform == 'mobile':
            app_binary_s3_path = usecase.get('app_binary_s3_path', {}).get('S', '')
            app_arn = usecase.get('app_arn', {}).get('S', '')
            if not app_binary_s3_path and not app_arn:
                return create_response(400, {
                    'error': 'Mobile usecase requires either app_binary_s3_path or app_arn to be set before execution'
                })

        # Handle different trigger types
        if trigger_type in ['Scheduled', 'OnDemandHeadless']:
            # Determine the correct S3 bucket based on execution region
            s3_bucket_prefix = os.environ['S3_BUCKET_PREFIX']
            execution_region = region if region else os.environ['DEFAULT_REGION']
            s3_bucket = f'{s3_bucket_prefix}-{execution_region}'

            print(f'Using S3 bucket for region {execution_region}: {s3_bucket}')
            print(f'Trigger MicroVM: {usecase_id}, {execution_id}')
            return start_microvm_execution(
                usecase_id, execution_id, usecase, test_platform, worker_token, execution_region, s3_bucket,
                suite_execution_id=suite_execution_id,
            )

        elif trigger_type == 'ci_runner':
            # CI/CD runner execution: create execution record only, no MicroVM
            print(f'CI/CD runner execution created: {execution_id}')
            return create_response(200, {
                'status': 'execution created',
                'usecaseId': usecase_id,
                'executionId': execution_id
            })
        
        else:
            # Should not reach here due to validation above, but keep for safety
            return create_response(400, {'error': f'Invalid trigger type: {trigger_type}'})
    
    except Exception as e:
        print(f'Error executing usecase: {str(e)}')
        return create_response(500, {'error': 'Failed to execute usecase'})
