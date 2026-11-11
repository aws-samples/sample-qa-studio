import lambda_init  # noqa: F401 — must be first import (run_payload / running_executions use pydantic from dependencies/)
import json
import os
import re
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from resource_auth import require_resource_access, app_from_body, new_usecase_owner_fields
from utils import create_response, get_table_name, get_current_timestamp, generate_uuid7
import microvm_launch
import running_executions
from run_payload import RunPayload

dynamodb = boto3.client('dynamodb')

REGION_PATTERN = re.compile(r'[a-z]{2}(-[a-z]+)+-\d')


def regional_bucket(region: str) -> str:
    """Artefact bucket in the browser's region (AgentCore records only to a
    same-region bucket; regional buckets replicate to the main one). Same
    naming as execute_usecase: ``{S3_BUCKET_PREFIX}-{region}``."""
    return f"{os.environ['S3_BUCKET_PREFIX']}-{region}"


def max_session_duration_s() -> int:
    """The VM's ``maximumDurationInSeconds``: configuration.json ``maxWizardSessionMinutes``."""
    return int(os.environ['MAX_WIZARD_SESSION_MINUTES']) * 60


def execution_key(usecase_id: str, session_id: str) -> dict:
    """Typed key of the wizard session's execution record."""
    return {
        'pk': {'S': f'USECASE_EXECUTION#{usecase_id}'},
        'sk': {'S': f'EXECUTION#{session_id}'},
    }


def update_session_microvm_info(usecase_id: str, session_id: str, microvm_id: str, cloudwatch_url: str) -> None:
    """Record the VM on the session's execution record (same fields as a batch execution)."""
    dynamodb.update_item(
        TableName=get_table_name(),
        Key=execution_key(usecase_id, session_id),
        UpdateExpression='SET microvm_id = :microvm_id, cloudwatch_logs_url = :cloudwatch_url',
        ExpressionAttributeValues={
            ':microvm_id': {'S': microvm_id},
            ':cloudwatch_url': {'S': cloudwatch_url},
        },
    )
    print(f'Updated wizard session {session_id} with MicroVM ID: {microvm_id}')


def record_running_session(usecase_id: str, session_id: str, microvm_id: str, max_duration_s: int) -> None:
    """Write the RUNNING_EXECUTIONS tracking record for the session's VM.

    Best-effort: the VM is already running and the execution record carries
    its id, so a failure here is logged and must not fail the launch — the
    reconciler only loses this session from its query until it ends.
    """
    record = running_executions.new_running_execution(
        execution_id=session_id,
        usecase_id=usecase_id,
        microvm_id=microvm_id,
        mode='wizard',
        max_duration_s=max_duration_s,
    )
    try:
        running_executions.put_running_execution(dynamodb, get_table_name(), record)
        print(f'Recorded running wizard session {session_id} (deadline {record.deadline})')
    except (ClientError, BotoCoreError) as e:
        print(f'Error recording running wizard session {session_id}: {str(e)}')


def mark_session_failed(usecase_id: str, session_id: str, error_msg: str) -> None:
    """``status = failed`` + ``wizard_status = closed`` on a session whose VM never started."""
    try:
        dynamodb.update_item(
            TableName=get_table_name(),
            Key=execution_key(usecase_id, session_id),
            UpdateExpression=(
                'SET #status = :status, wizard_status = :wizard_status, '
                'completed_at = :completed_at, error_message = :error_msg'
            ),
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': {'S': 'failed'},
                ':wizard_status': {'S': 'closed'},
                ':completed_at': {'S': get_current_timestamp()},
                ':error_msg': {'S': error_msg},
            },
        )
        print(f'Marked wizard session {session_id} failed: {error_msg}')
    except Exception as e:  # noqa: BLE001 — the launch error is what the caller reports
        print(f'Error marking wizard session {session_id} failed: {str(e)}')


def start_session_microvm(usecase_id: str, session_id: str, executing_region: str) -> dict:
    """Launch the wizard worker's MicroVM and record its identifiers.

    Mirrors ``execute_usecase.start_microvm_execution``: per-session values
    travel in the run-hook payload (``RunPayload(mode='wizard')``), stack
    constants are image-level env. The VM runs in the stack region
    (``AWS_REGION``); ``executing_region`` only selects the browser region and
    its artefact bucket. Any failure (after the throttling retries) marks the
    session ``failed`` and returns 500.
    """
    try:
        max_duration_s = max_session_duration_s()
        log_group = os.environ['MICROVM_LOG_GROUP']
        payload = RunPayload(
            mode='wizard',
            usecase_id=usecase_id,
            session_id=session_id,
            region=executing_region,
            s3_bucket=regional_bucket(executing_region),
            max_duration_s=max_duration_s,
        )
        result = microvm_launch.launch_microvm(
            microvm_launch.get_microvm_client(),
            image_arn=os.environ['MICROVM_IMAGE_ARN'],
            image_version=os.environ['MICROVM_IMAGE_VERSION'],
            execution_role_arn=os.environ['MICROVM_EXECUTION_ROLE_ARN'],
            log_group=log_group,
            log_stream=session_id,
            payload=payload,
            max_duration_s=max_duration_s,
            client_token=session_id,
        )
        microvm_id = result['microvmId']
        print(f'MicroVM started for wizard session {session_id} - ID: {microvm_id}, state: {result.get("state")}')

        cloudwatch_url = microvm_launch.microvm_cloudwatch_logs_url(os.environ['AWS_REGION'], log_group, session_id)
        update_session_microvm_info(usecase_id, session_id, microvm_id, cloudwatch_url)
        record_running_session(usecase_id, session_id, microvm_id, max_duration_s)

        return create_response(201, {
            'sessionId': session_id,
            'usecaseId': usecase_id,
            'status': 'initializing',
            'microvmId': microvm_id,
        })
    except Exception as e:  # noqa: BLE001 — every launch failure ends the session the same way
        error_msg = f'Failed to start MicroVM: {str(e)}'
        print(f'Error starting wizard session MicroVM: {error_msg}')
        mark_session_failed(usecase_id, session_id, error_msg)
        return create_response(500, {'error': error_msg})


@require_resource_access('edit', app_from_body('application_id'), scopes=['api/usecases.write'])
def handler(event, context):
    """
    Start a wizard session by creating a usecase, an execution and the
    wizard worker's Lambda MicroVM (``RunPayload(mode='wizard')``).
    
    Request Body:
    - application_id: Application the new use case belongs to (required;
      edit on it is checked by the decorator)
    - name: Name of the wizard session (required)
    - starting_url: Starting URL for the wizard (required)
    - description: Optional description
    - executing_region: AWS region the browser runs in (defaults to DEFAULT_REGION)
    - model_id: Model ID (defaults to nova-act-v1.0)
    - tags: Optional list of tags
    
    Returns:
    - 201: Wizard session created successfully (``sessionId``, ``usecaseId``,
      ``status``, ``microvmId``)
    - 400: Missing required fields
    - 403: Insufficient scopes or no edit access to the application
    - 404: Application not found
    - 500: Error creating session (a failed launch leaves the session ``failed``)
    """
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return create_response(400, {'error': 'Invalid JSON in request body'})
    
    name = body.get('name', '').strip()
    starting_url = body.get('starting_url', '').strip()
    description = body.get('description', '')
    executing_region = body.get('executing_region', '').strip()
    # Use default region if empty
    if not executing_region:
        executing_region = os.environ.get('DEFAULT_REGION', 'us-east-1')
    model_id = body.get('model_id', 'nova-act-v1.0')
    tags = body.get('tags', [])
    
    # Validate required fields
    if not name or not starting_url:
        return create_response(400, {'error': 'name and starting_url are required'})
    # The region becomes part of the artefact bucket name.
    if not REGION_PATTERN.fullmatch(executing_region):
        return create_response(400, {'error': f'Invalid executing_region: {executing_region}'})
    
    print(f'Starting wizard session: name={name}, starting_url={starting_url}, executing_region={executing_region}')
    
    table_name = get_table_name()
    
    # Generate IDs (UUIDv7 for time-ordered sorting)
    usecase_id = generate_uuid7()
    session_id = generate_uuid7()
    created_at = get_current_timestamp()
    
    try:
        owner_fields = {key: {'S': value}
                        for key, value in new_usecase_owner_fields(body['application_id']).items()}

        # Create usecase record
        dynamodb.put_item(
            TableName=table_name,
            Item={
                **owner_fields,
                'pk': {'S': 'USECASES'},
                'sk': {'S': f'USECASE#{usecase_id}'},
                'id': {'S': usecase_id},
                'name': {'S': name},
                'description': {'S': description},
                'starting_url': {'S': starting_url},
                'active': {'BOOL': True},
                'tags': {'L': [{'S': tag} for tag in tags]},
                'created_at': {'S': created_at},
                'executing_region': {'S': executing_region},
                'model_id': {'S': model_id}
            }
        )
        print(f'Created usecase {usecase_id}')
        
        # Create wizard execution record
        dynamodb.put_item(
            TableName=table_name,
            Item={
                **execution_key(usecase_id, session_id),
                'starting_url': {'S': starting_url},
                'status': {'S': 'pending'},
                'created_at': {'S': created_at},
                'trigger_type': {'S': 'Wizard'},
                'executing_region': {'S': executing_region},
                'model_id': {'S': model_id},
                'mode': {'S': 'wizard'},
                'wizard_status': {'S': 'active'},
                'last_activity': {'S': created_at}
            }
        )
        print(f'Created execution {session_id} for usecase {usecase_id}')
    except Exception as e:  # noqa: BLE001 — nothing to clean up: no VM was launched
        print(f'Error starting wizard session: {str(e)}')
        return create_response(500, {'error': 'Failed to start wizard session'})

    return start_session_microvm(usecase_id, session_id, executing_region)
