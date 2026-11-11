"""Tests for the wizard's AgentCore browser creation (``browser.py``).

The control-plane client is faked; the request body must match the CLI's
``build_browser_config`` (one implementation for batch and wizard) in both
network modes.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import browser  # noqa: E402

_VPC_ENV = {
    'AGENT_CORE_VPC': 'true',
    'AC_VPC_ID': 'vpc-1',
    'AC_SUBNET_IDS': 'subnet-b,subnet-a',
    'AC_SECURITY_GROUP_ID': 'sg-1',
}


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv('BEDROCK_EXECUTION_ROLE', 'arn:aws:iam::1:role/nova-act')
    for name in ('AGENT_CORE_VPC', 'AC_VPC_ID', 'AC_SUBNET_ID', 'AC_SUBNET_IDS', 'AC_SECURITY_GROUP_ID'):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.fixture
def control_client():
    client = MagicMock()
    client.create_browser.return_value = {'browserId': 'b-1', 'status': 'CREATING'}
    client.get_browser.return_value = {'status': 'READY'}
    with patch.object(browser, '_create_client', return_value=client) as factory:
        client.factory = factory
        yield client


def _create(policy=None):
    return browser.create_browser(
        'abc12', 'wiz-1', 'artefacts', 'uc-1/wiz-1/recording/', 'eu-west-1',
        browser_policy_s3_path=policy,
    )


def test_public_by_default(env, control_client):
    assert _create() == 'b-1'
    kwargs = control_client.create_browser.call_args.kwargs
    assert kwargs['networkConfiguration'] == {'networkMode': 'PUBLIC'}
    assert kwargs['name'] == 'nova_act_qa_studio_abc12'
    control_client.factory.assert_called_once_with('eu-west-1')


def test_flag_false_is_public_even_with_ac_vars(env, control_client):
    for key, value in _VPC_ENV.items():
        env.setenv(key, value)
    env.setenv('AGENT_CORE_VPC', 'false')
    _create()
    assert control_client.create_browser.call_args.kwargs['networkConfiguration'] == {'networkMode': 'PUBLIC'}


def test_vpc_mode_passes_every_subnet_and_the_security_group(env, control_client):
    for key, value in _VPC_ENV.items():
        env.setenv(key, value)
    _create()
    assert control_client.create_browser.call_args.kwargs['networkConfiguration'] == {
        'networkMode': 'VPC',
        'vpcConfig': {'securityGroups': ['sg-1'], 'subnets': ['subnet-b', 'subnet-a']},
    }


def test_vpc_mode_missing_var_raises_before_create_browser(env, control_client):
    env.setenv('AGENT_CORE_VPC', 'true')
    env.setenv('AC_VPC_ID', 'vpc-1')
    env.setenv('AC_SUBNET_ID', 'subnet-legacy')  # the old single-subnet var is not read
    with pytest.raises(RuntimeError, match='AC_SUBNET_IDS'):
        _create()
    control_client.create_browser.assert_not_called()
    control_client.factory.assert_not_called()


@pytest.mark.parametrize('vpc', [False, True])
def test_policy_and_recording_identical_in_both_modes(env, control_client, vpc):
    if vpc:
        for key, value in _VPC_ENV.items():
            env.setenv(key, value)
    _create(policy='policies/uc-1.json')
    kwargs = control_client.create_browser.call_args.kwargs
    assert kwargs['recording'] == {
        'enabled': True,
        's3Location': {'bucket': 'artefacts', 'prefix': 'uc-1/wiz-1/recording/'},
    }
    assert kwargs['enterprisePolicies'] == [
        {'type': 'MANAGED', 'location': {'s3': {'bucket': 'artefacts', 'prefix': 'policies/uc-1.json'}}},
    ]
    assert kwargs['executionRoleArn'] == 'arn:aws:iam::1:role/nova-act'


def test_request_matches_cli_builder(env, control_client):
    """One implementation: the wizard sends exactly what the CLI builds."""
    from qa_studio_cli.runner.browser.agentcore import build_browser_config

    for key, value in _VPC_ENV.items():
        env.setenv(key, value)
    _create(policy='p.json')
    sent = dict(control_client.create_browser.call_args.kwargs)
    expected = build_browser_config(
        unique_id='abc12', execution_id='wiz-1', artefact_bucket='artefacts',
        artefact_prefix='uc-1/wiz-1/recording/', browser_policy_s3_path='p.json',
    )
    sent.pop('clientToken')
    expected.pop('clientToken')
    assert sent == expected
