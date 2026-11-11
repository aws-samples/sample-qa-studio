"""``RUNNING_EXECUTIONS`` / ``EXECUTION#{execution_id}`` tracking records.

One item per in-flight MicroVM execution, written right after a successful
``RunMicrovm`` and deleted on every terminal transition
(``update_execution_status``, ``stop_execution``, the reconciler).  The
partition is bounded by the MicroVM concurrency quota (≤ ~50 items), so the
reconciler *queries* it instead of scanning the table for executions whose VM
has gone away.

All helpers take the low-level ``boto3.client('dynamodb')`` the launch and
status Lambdas already hold; items are (de)serialised with ``TypeSerializer`` /
``TypeDeserializer``.
"""
import lambda_init  # noqa: F401 — must be first import (pydantic lives in dependencies/)
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)

RUNNING_EXECUTIONS_PK = 'RUNNING_EXECUTIONS'
_SK_PREFIX = 'EXECUTION#'

#: Slack after the VM's ``maximumDurationInSeconds`` before the reconciler
#: treats an execution as overdue (platform kill + runner teardown latency).
DEADLINE_GRACE = timedelta(minutes=10)

#: Same RFC3339 shape as ``utils.get_current_timestamp``.
_TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%SZ'

RunningMode = Literal['batch', 'wizard']


def running_execution_sk(execution_id: str) -> str:
    return f'{_SK_PREFIX}{execution_id}'


def running_execution_key(execution_id: str) -> dict:
    """Plain (untyped) key of the tracking record."""
    return {'pk': RUNNING_EXECUTIONS_PK, 'sk': running_execution_sk(execution_id)}


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime(_TIMESTAMP_FORMAT)


def _parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value, _TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)


class RunningExecutionRecord(BaseModel):
    """The stored item. Unknown attributes are ignored on read so a newer
    writer never breaks the reconciler; writes always go through this model."""

    model_config = ConfigDict(extra='ignore', frozen=True)

    pk: Literal['RUNNING_EXECUTIONS'] = RUNNING_EXECUTIONS_PK
    sk: str = Field(pattern=r'^EXECUTION#.+')
    usecase_id: str
    microvm_id: str
    mode: RunningMode
    started_at: str
    deadline: str
    suite_execution_id: Optional[str] = None

    @field_validator('started_at', 'deadline')
    @classmethod
    def _rfc3339(cls, value: str) -> str:
        _parse_timestamp(value)  # raises ValueError → ValidationError
        return value

    @property
    def execution_id(self) -> str:
        return self.sk[len(_SK_PREFIX):]

    def started_at_dt(self) -> datetime:
        return _parse_timestamp(self.started_at)

    def deadline_at(self) -> datetime:
        return _parse_timestamp(self.deadline)


def new_running_execution(
    *,
    execution_id: str,
    usecase_id: str,
    microvm_id: str,
    mode: RunningMode,
    max_duration_s: int,
    suite_execution_id: Optional[str] = None,
    started_at: Optional[datetime] = None,
) -> RunningExecutionRecord:
    """Build the record for a VM launched now (or at ``started_at``);
    ``deadline = started_at + max_duration_s + DEADLINE_GRACE``."""
    started = started_at or datetime.now(timezone.utc)
    deadline = started + timedelta(seconds=max_duration_s) + DEADLINE_GRACE
    return RunningExecutionRecord(
        sk=running_execution_sk(execution_id),
        usecase_id=usecase_id,
        microvm_id=microvm_id,
        mode=mode,
        started_at=_format_timestamp(started),
        deadline=_format_timestamp(deadline),
        suite_execution_id=suite_execution_id,
    )


def _typed_key(execution_id: str) -> dict:
    serializer = TypeSerializer()
    return {name: serializer.serialize(value) for name, value in running_execution_key(execution_id).items()}


def put_running_execution(dynamodb_client, table_name: str, record: RunningExecutionRecord) -> None:
    """Write the record (errors propagate; the launcher decides they must not fail the launch)."""
    serializer = TypeSerializer()
    item = {name: serializer.serialize(value) for name, value in record.model_dump(exclude_none=True).items()}
    dynamodb_client.put_item(TableName=table_name, Item=item)


def clear_running_execution(dynamodb_client, table_name: str, execution_id: str) -> bool:
    """Best-effort delete of the tracking record.

    Idempotent (DeleteItem on a missing key succeeds) and never raises: the
    caller has already written the terminal status, and a stale tracking
    record is reconciled later anyway.  Returns ``False`` when the delete failed.
    """
    try:
        dynamodb_client.delete_item(TableName=table_name, Key=_typed_key(execution_id))
        return True
    except (ClientError, BotoCoreError) as e:
        logger.warning('Failed to clear RUNNING_EXECUTIONS record for execution %s: %s', execution_id, e)
        return False


def list_running_executions(dynamodb_client, table_name: str) -> List[RunningExecutionRecord]:
    """Every tracking record (one bounded-partition Query, paginated; never a Scan)."""
    deserializer = TypeDeserializer()
    records: List[RunningExecutionRecord] = []
    kwargs = {
        'TableName': table_name,
        'KeyConditionExpression': 'pk = :pk',
        'ExpressionAttributeValues': {':pk': {'S': RUNNING_EXECUTIONS_PK}},
    }
    while True:
        response = dynamodb_client.query(**kwargs)
        for item in response.get('Items', []):
            plain = {name: deserializer.deserialize(value) for name, value in item.items()}
            records.append(RunningExecutionRecord.model_validate(plain))
        last_key = response.get('LastEvaluatedKey')
        if not last_key:
            return records
        kwargs['ExclusiveStartKey'] = last_key
