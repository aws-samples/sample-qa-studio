import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict
import boto3
from boto3.dynamodb.conditions import Key
from utils import create_response, get_table_name, require_scopes, validate_path_id

logger = logging.getLogger()
logger.setLevel(logging.INFO)

NAMESPACE = 'QAStudio/Executions'


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    user_identity, error_response = require_scopes(event, ['api/applications.read'])
    if error_response:
        return error_response

    app_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'application ID')
    if error:
        return error

    try:
        query_params = event.get('queryStringParameters') or {}
        window = query_params.get('window', '7d')
        env_filter = query_params.get('env', '')

        days = 30 if window == '30d' else 7
        period = 86400 if window == '30d' else 3600
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(days=days)

        dimensions = [{'Name': 'ApplicationId', 'Value': app_id}]
        if env_filter:
            dimensions.append({'Name': 'Environment', 'Value': env_filter})

        cloudwatch = boto3.client('cloudwatch')

        metric_queries = [
            {
                'Id': 'executions',
                'MetricStat': {
                    'Metric': {'Namespace': NAMESPACE, 'MetricName': 'ExecutionCount', 'Dimensions': dimensions},
                    'Period': period,
                    'Stat': 'Sum',
                },
            },
            {
                'Id': 'successes',
                'MetricStat': {
                    'Metric': {'Namespace': NAMESPACE, 'MetricName': 'SuccessCount', 'Dimensions': dimensions},
                    'Period': period,
                    'Stat': 'Sum',
                },
            },
            {
                'Id': 'failures',
                'MetricStat': {
                    'Metric': {'Namespace': NAMESPACE, 'MetricName': 'FailureCount', 'Dimensions': dimensions},
                    'Period': period,
                    'Stat': 'Sum',
                },
            },
            {
                'Id': 'duration',
                'MetricStat': {
                    'Metric': {'Namespace': NAMESPACE, 'MetricName': 'DurationMs', 'Dimensions': dimensions},
                    'Period': period,
                    'Stat': 'Average',
                },
            },
        ]

        response = cloudwatch.get_metric_data(
            MetricDataQueries=metric_queries,
            StartTime=start_time,
            EndTime=now,
            ScanBy='TimestampAscending',
        )

        results = {r['Id']: r for r in response.get('MetricDataResults', [])}

        date_fmt = '%Y-%m-%dT%H:%M:%SZ' if period == 3600 else '%Y-%m-%d'
        dates = [t.strftime(date_fmt) for t in results.get('executions', {}).get('Timestamps', [])]
        exec_values = [int(v) for v in results.get('executions', {}).get('Values', [])]
        success_values = [int(v) for v in results.get('successes', {}).get('Values', [])]
        failure_values = [int(v) for v in results.get('failures', {}).get('Values', [])]
        duration_values = [int(v) for v in results.get('duration', {}).get('Values', [])]

        total_exec = sum(exec_values)
        total_success = sum(success_values)
        total_failures = sum(failure_values)
        pass_rate = round((total_success / total_exec * 100), 1) if total_exec > 0 else 0
        avg_duration = int(sum(duration_values) / len(duration_values)) if duration_values else 0

        # Compute health score: pass_rate - flaky_penalty
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())

        flaky_response = table.query(
            KeyConditionExpression=Key('pk').eq(f'APPLICATION_FLAKY#{app_id}')
        )
        flaky_count = sum(1 for item in flaky_response.get('Items', []) if item.get('flip_count_7d', 0) > 0)
        flaky_penalty = (flaky_count / max(total_exec, 1)) * 25
        health_score = max(0, min(100, round(pass_rate - flaky_penalty)))

        return create_response(200, {
            'application_id': app_id,
            'window': window,
            'environment': env_filter or 'all',
            'series': {
                'dates': dates,
                'executions': exec_values,
                'successes': success_values,
                'failures': failure_values,
                'avg_duration_ms': duration_values,
            },
            'totals': {
                'total_executions': total_exec,
                'pass_rate': pass_rate,
                'avg_duration_ms': avg_duration,
            },
            'health_score': health_score,
        })
    except Exception as e:
        logger.error(f"Error fetching metrics for app {app_id}: {e}", exc_info=True)
        return create_response(500, {'error': f'Failed to fetch metrics: {str(e)}'})
