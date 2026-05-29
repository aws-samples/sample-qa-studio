import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict
import boto3
from boto3.dynamodb.conditions import Key
from utils import create_response, get_table_name, require_scopes

logger = logging.getLogger()
logger.setLevel(logging.INFO)

NAMESPACE = 'QAStudio/Executions'


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    user_identity, error_response = require_scopes(event, ['api/applications.read'])
    if error_response:
        return error_response

    query_params = event.get('queryStringParameters') or {}
    window = query_params.get('window', '7d')
    days = 30 if window == '30d' else 7
    period = 86400 if window == '30d' else 3600

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(get_table_name())

    # Fetch all applications
    index_response = table.query(
        KeyConditionExpression=Key('pk').eq('APPLICATIONS') & Key('sk').begins_with('APPLICATION#')
    )
    app_ids = [item['id'] for item in index_response.get('Items', [])]

    if not app_ids:
        return create_response(200, [])

    # Batch get metadata
    keys = [{'pk': f'APPLICATION#{aid}', 'sk': 'METADATA'} for aid in app_ids]
    batch_response = dynamodb.batch_get_item(
        RequestItems={get_table_name(): {'Keys': keys}}
    )
    apps = batch_response.get('Responses', {}).get(get_table_name(), [])

    # Fetch CloudWatch metrics for all apps
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(days=days)
    cloudwatch = boto3.client('cloudwatch')

    overview_items = []
    for app in apps:
        app_id = app['id']
        dimensions = [{'Name': 'ApplicationId', 'Value': app_id}]

        try:
            cw_response = cloudwatch.get_metric_data(
                MetricDataQueries=[
                    {
                        'Id': 'executions',
                        'MetricStat': {
                            'Metric': {'Namespace': NAMESPACE, 'MetricName': 'ExecutionCount', 'Dimensions': dimensions},
                            'Period': period, 'Stat': 'Sum',
                        },
                    },
                    {
                        'Id': 'successes',
                        'MetricStat': {
                            'Metric': {'Namespace': NAMESPACE, 'MetricName': 'SuccessCount', 'Dimensions': dimensions},
                            'Period': period, 'Stat': 'Sum',
                        },
                    },
                    {
                        'Id': 'failures',
                        'MetricStat': {
                            'Metric': {'Namespace': NAMESPACE, 'MetricName': 'FailureCount', 'Dimensions': dimensions},
                            'Period': period, 'Stat': 'Sum',
                        },
                    },
                ],
                StartTime=start_time,
                EndTime=now,
                ScanBy='TimestampAscending',
            )

            results = {r['Id']: r for r in cw_response.get('MetricDataResults', [])}
            exec_values = [int(v) for v in results.get('executions', {}).get('Values', [])]
            success_values = [int(v) for v in results.get('successes', {}).get('Values', [])]
            failure_values = [int(v) for v in results.get('failures', {}).get('Values', [])]
            date_fmt = '%Y-%m-%dT%H:%M:%SZ' if period == 3600 else '%Y-%m-%d'
            dates = [t.strftime(date_fmt) for t in results.get('executions', {}).get('Timestamps', [])]

            total_exec = sum(exec_values)
            total_success = sum(success_values)
            total_failures = sum(failure_values)
            pass_rate = round((total_success / total_exec * 100), 1) if total_exec > 0 else 0
        except Exception as e:
            logger.warning(f"CloudWatch query failed for app {app_id}: {e}")
            total_exec = 0
            total_failures = 0
            pass_rate = 0
            dates = []
            success_values = []
            failure_values = []

        app.pop('pk', None)
        app.pop('sk', None)
        app['pass_rate'] = pass_rate
        app['total_executions'] = total_exec
        app['failure_count'] = total_failures
        app['series'] = {
            'dates': dates,
            'successes': success_values,
            'failures': failure_values,
        }
        overview_items.append(app)

    # Sort: most failures first, then alphabetical
    overview_items.sort(key=lambda x: (-x.get('failure_count', 0), x.get('name', '').lower()))

    return create_response(200, overview_items)
