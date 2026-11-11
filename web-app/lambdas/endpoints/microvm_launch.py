"""Launch a worker MicroVM (``lambda-microvms.RunMicrovm``).

Shared by the launch Lambdas (``execute_usecase`` today, ``start_wizard_session``
in phase 2): one place for the RunMicrovm parameters the spike verified, the
``ThrottlingException`` retry loop (regional RunMicrovm quota is 5/s, burst 5;
a suite fan-out hits it), the managed network-connector ARNs and the
CloudWatch Logs deep link for the VM's stream.

The ``lambda-microvms`` client is created lazily: the ``ecs`` path never needs
it and older botocore (some test environments) does not know the service.
"""
import lambda_init  # noqa: F401 — must be first import (run_payload uses pydantic from dependencies/)
import time
from typing import Optional
from urllib.parse import quote

import boto3
from botocore.exceptions import ClientError

from run_payload import RunPayload

#: ``idlePolicy.maxIdleDurationSeconds`` platform minimum. The policy cannot be
#: disabled; a batch VM has no inbound traffic, so it is set to the VM's own
#: maximum duration (clamped up to this) and never suspends a running test.
MIN_IDLE_DURATION_S = 60

#: RunMicrovm attempts on ``ThrottlingException`` (quota 5/s, burst 5).
RUN_MICROVM_ATTEMPTS = 5

_client = None


def get_microvm_client():
    """The module's ``lambda-microvms`` client, created on first use."""
    global _client
    if _client is None:
        _client = boto3.client('lambda-microvms')
    return _client


def no_ingress_connector_arn(region: str) -> str:
    """Managed connector that blocks all inbound traffic (omitting it yields HTTP_INGRESS)."""
    return f'arn:aws:lambda:{region}:aws:network-connector:aws-network-connector:NO_INGRESS'


def microvm_cloudwatch_logs_url(region: str, log_group: str, log_stream: str) -> str:
    """Deep link to the VM's CloudWatch Logs stream (same format as the ECS link)."""
    return (
        f"https://{region}.console.aws.amazon.com/cloudwatch/home?"
        f"region={region}#logsV2:log-groups/log-group/{quote(log_group)}"
        f"/log-events/{quote(log_stream)}"
    )


def launch_microvm(
    client,
    *,
    image_arn: str,
    image_version: str,
    execution_role_arn: str,
    log_group: str,
    log_stream: str,
    payload: RunPayload,
    max_duration_s: int,
    client_token: Optional[str] = None,
) -> dict:
    """Call ``RunMicrovm`` and return its response (``microvmId``, ``state``, ...).

    The VM runs in the client's region; the ingress connector ARN is built for
    that region. ``egressNetworkConnectors`` is omitted on purpose: the default
    is internet egress and explicit connector ARNs are rejected (spike).
    Retries ``ThrottlingException`` with exponential backoff up to
    :data:`RUN_MICROVM_ATTEMPTS` times; every other error propagates.
    Raises ``PayloadTooLargeError`` before any call when the payload exceeds
    the 4096-byte ``runHookPayload`` limit.
    """
    region = client.meta.region_name
    kwargs = {
        'imageIdentifier': image_arn,
        'imageVersion': image_version,
        'executionRoleArn': execution_role_arn,
        'ingressNetworkConnectors': [no_ingress_connector_arn(region)],
        'idlePolicy': {
            'maxIdleDurationSeconds': max(max_duration_s, MIN_IDLE_DURATION_S),
            'suspendedDurationSeconds': 0,
            'autoResumeEnabled': False,
        },
        'logging': {'cloudWatch': {'logGroup': log_group, 'logStream': log_stream}},
        'runHookPayload': payload.to_hook_payload(),
        'maximumDurationInSeconds': max_duration_s,
    }
    if client_token:
        kwargs['clientToken'] = client_token

    for attempt in range(RUN_MICROVM_ATTEMPTS):
        try:
            return client.run_microvm(**kwargs)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ThrottlingException' and attempt < RUN_MICROVM_ATTEMPTS - 1:
                wait = 2 ** attempt
                print(f'RunMicrovm throttled, retry {attempt + 1}/{RUN_MICROVM_ATTEMPTS} in {wait}s')
                time.sleep(wait)
            else:
                raise
    raise RuntimeError('unreachable: RunMicrovm loop exited without returning or raising')
