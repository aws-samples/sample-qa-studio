import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict
import boto3
from utils import get_table_name

logger = logging.getLogger()
logger.setLevel(logging.INFO)

NAMESPACE = 'QAStudio/Executions'
TERMINAL_STATUSES = {'success', 'failed'}
TTL_DAYS = 30


def handler(event: Dict[str, Any], context: Any) -> None:
    detail = event.get('detail', {})
    usecase_id = detail.get('usecase_id')
    execution_id = detail.get('execution_id')
    status = detail.get('status')
    timestamp = detail.get('timestamp', '')

    logger.info(f"Aggregation event: usecase={usecase_id} execution={execution_id} status={status}")

    if status not in TERMINAL_STATUSES:
        logger.info(f"Ignoring non-terminal status: {status}")
        return

    if not usecase_id or not execution_id:
        logger.error("Missing usecase_id or execution_id")
        return

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(get_table_name())

    # 1. Look up usecase -> get application_id
    usecase_response = table.get_item(Key={'pk': 'USECASES', 'sk': f'USECASE#{usecase_id}'})
    usecase = usecase_response.get('Item')
    if not usecase:
        logger.warning(f"Usecase {usecase_id} not found")
        return

    application_id = usecase.get('application_id', '')
    if not application_id:
        logger.info(f"Usecase {usecase_id} has no application_id, skipping aggregation")
        return

    # 2. Look up execution record -> get duration, trigger_type
    exec_response = table.get_item(
        Key={'pk': f'USECASE_EXECUTION#{usecase_id}', 'sk': f'EXECUTION#{execution_id}'}
    )
    execution = exec_response.get('Item', {})
    created_at = execution.get('createdAt', '')
    completed_at = execution.get('completedAt', timestamp)
    trigger_type = execution.get('triggerType', 'OnDemand')

    duration_ms = 0
    if created_at and completed_at:
        try:
            start = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            end = datetime.fromisoformat(completed_at.replace('Z', '+00:00'))
            duration_ms = int((end - start).total_seconds() * 1000)
        except (ValueError, TypeError):
            logger.warning("Could not compute duration")

    # Get environment from usecase association
    assoc_response = table.get_item(
        Key={'pk': f'APPLICATION#{application_id}', 'sk': f'USECASE#{usecase_id}'}
    )
    environment = assoc_response.get('Item', {}).get('environment', 'default')

    # 3. Publish CloudWatch metrics
    _publish_metrics(application_id, environment, trigger_type, status, duration_ms)

    # 4. Update Application METADATA
    table.update_item(
        Key={'pk': f'APPLICATION#{application_id}', 'sk': 'METADATA'},
        UpdateExpression='SET last_execution_id = :eid, last_execution_status = :status, last_execution_at = :ts',
        ExpressionAttributeValues={
            ':eid': execution_id,
            ':status': status,
            ':ts': timestamp,
        },
    )

    # 5. If failed, write failure record
    if status == 'failed':
        ttl = int(time.time()) + (TTL_DAYS * 86400)
        error_message = detail.get('error_message', '')
        usecase_name = usecase.get('name', '')
        table.put_item(Item={
            'pk': f'APPLICATION_FAILURES#{application_id}',
            'sk': f'FAILURE#{timestamp}#{execution_id}',
            'usecase_id': usecase_id,
            'usecase_name': usecase_name,
            'error_message': error_message,
            'execution_id': execution_id,
            'environment': environment,
            'ttl': ttl,
        })

    # 6. Flakiness check
    usecase_name = usecase.get('name', '')
    _update_flakiness(table, application_id, usecase_id, usecase_name, status, timestamp)

    logger.info(f"Aggregation complete for app={application_id} execution={execution_id}")


def _publish_metrics(app_id: str, environment: str, trigger_type: str, status: str, duration_ms: int) -> None:
    cloudwatch = boto3.client('cloudwatch')
    is_success = 1 if status == 'success' else 0
    is_failure = 1 if status == 'failed' else 0

    environment = environment or 'default'
    trigger_type = trigger_type or 'OnDemand'

    base_metric_data = [
        {'MetricName': 'ExecutionCount', 'Value': 1, 'Unit': 'Count'},
        {'MetricName': 'SuccessCount', 'Value': is_success, 'Unit': 'Count'},
        {'MetricName': 'FailureCount', 'Value': is_failure, 'Unit': 'Count'},
        {'MetricName': 'DurationMs', 'Value': duration_ms, 'Unit': 'Milliseconds'},
    ]

    dimension_sets = [
        [{'Name': 'ApplicationId', 'Value': app_id}],
        [{'Name': 'ApplicationId', 'Value': app_id}, {'Name': 'Environment', 'Value': environment}],
        [{'Name': 'ApplicationId', 'Value': app_id}, {'Name': 'TriggerType', 'Value': trigger_type}],
        [{'Name': 'ApplicationId', 'Value': app_id}, {'Name': 'Environment', 'Value': environment}, {'Name': 'TriggerType', 'Value': trigger_type}],
        [],
    ]

    metric_data = []
    now = datetime.now(timezone.utc)

    for dims in dimension_sets:
        for metric in base_metric_data:
            entry = {
                'MetricName': metric['MetricName'],
                'Value': metric['Value'],
                'Unit': metric['Unit'],
                'Timestamp': now,
            }
            if dims:
                entry['Dimensions'] = dims
            metric_data.append(entry)

    # CloudWatch accepts max 1000 metric data points per call; we have 20
    try:
        cloudwatch.put_metric_data(Namespace=NAMESPACE, MetricData=metric_data)
    except Exception as e:
        logger.error(f"Failed to publish CloudWatch metrics: {e}")


def _update_flakiness(table, app_id: str, usecase_id: str, usecase_name: str, status: str, timestamp: str) -> None:
    flaky_key = {'pk': f'APPLICATION_FLAKY#{app_id}', 'sk': f'USECASE#{usecase_id}'}

    response = table.get_item(Key=flaky_key)
    item = response.get('Item')

    if not item:
        table.put_item(Item={
            **flaky_key,
            'usecase_id': usecase_id,
            'usecase_name': usecase_name,
            'last_status': status,
            'flip_count_7d': 0,
            'flip_count_30d': 0,
            'last_flip_at': '',
        })
        return

    last_status = item.get('last_status', '')
    if last_status and last_status != status:
        table.update_item(
            Key=flaky_key,
            UpdateExpression='SET last_status = :status, flip_count_7d = flip_count_7d + :one, flip_count_30d = flip_count_30d + :one, last_flip_at = :ts, usecase_name = :name',
            ExpressionAttributeValues={':status': status, ':one': 1, ':ts': timestamp, ':name': usecase_name},
        )
    else:
        table.update_item(
            Key=flaky_key,
            UpdateExpression='SET last_status = :status, usecase_name = :name',
            ExpressionAttributeValues={':status': status, ':name': usecase_name},
        )
