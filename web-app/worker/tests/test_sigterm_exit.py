"""``utils.install_sigterm_exit``: SIGTERM → ``SystemExit(143)`` in the wizard worker.

Python's default SIGTERM disposition kills the interpreter without running
``finally`` blocks, so the MicroVM ``/terminate`` hook (SIGTERM to the child's
process group) left ``wizard_worker.py``'s AgentCore browser and live-view
record behind.  ``SystemExit`` is a ``BaseException``: the worker's
``except Exception`` blocks do not swallow it, its ``finally`` cleanup runs,
and nothing writes ``failed`` (the record is already ``success`` / ``timeout``).
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import SIGTERM_EXIT_CODE, install_sigterm_exit  # noqa: E402


@pytest.fixture
def restore_sigterm():
    previous = signal.getsignal(signal.SIGTERM)
    yield
    signal.signal(signal.SIGTERM, previous)


def test_exit_code_is_the_conventional_sigterm_code():
    assert SIGTERM_EXIT_CODE == 128 + signal.SIGTERM == 143


def test_installs_a_handler_that_raises_system_exit_143(restore_sigterm):
    logger = logging.getLogger('test_sigterm_exit')
    install_sigterm_exit(logger)

    handler = signal.getsignal(signal.SIGTERM)
    assert callable(handler)
    assert handler not in (signal.SIG_DFL, signal.SIG_IGN)
    with pytest.raises(SystemExit) as raised:
        handler(signal.SIGTERM, None)
    assert raised.value.code == 143


def test_handler_logs_one_line_when_the_signal_arrives(restore_sigterm, caplog):
    logger = logging.getLogger('test_sigterm_exit.log')
    install_sigterm_exit(logger)
    with caplog.at_level(logging.INFO, logger='test_sigterm_exit.log'), pytest.raises(SystemExit):
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
    messages = [r.getMessage() for r in caplog.records if r.name == 'test_sigterm_exit.log']
    assert len(messages) == 1
    assert 'SIGTERM' in messages[0]


def test_a_real_signal_to_the_process_raises_system_exit_in_the_main_thread(restore_sigterm):
    install_sigterm_exit(logging.getLogger('test_sigterm_exit.real'))
    finally_ran = False
    with pytest.raises(SystemExit) as raised:
        try:
            os.kill(os.getpid(), signal.SIGTERM)
            # Give the interpreter a bytecode boundary to deliver the signal on.
            for _ in range(1000):
                pass
        finally:
            finally_ran = True
    assert raised.value.code == 143
    assert finally_ran


def test_off_the_main_thread_is_a_no_op_with_a_warning(restore_sigterm, caplog):
    before = signal.getsignal(signal.SIGTERM)
    logger = logging.getLogger('test_sigterm_exit.thread')
    outcome: dict = {}

    def run():
        with caplog.at_level(logging.WARNING, logger='test_sigterm_exit.thread'):
            try:
                install_sigterm_exit(logger)
                outcome['ok'] = True
            except Exception as exc:  # noqa: BLE001 — the test asserts no exception
                outcome['error'] = exc

    worker = threading.Thread(target=run)
    worker.start()
    worker.join(5)

    assert outcome == {'ok': True}
    assert signal.getsignal(signal.SIGTERM) is before
    assert any('main thread' in r.getMessage() for r in caplog.records if r.name == 'test_sigterm_exit.thread')


# ── wizard_worker.main(): SystemExit passes both ``except Exception`` blocks ──

from unittest.mock import MagicMock, patch  # noqa: E402

import wizard_worker  # noqa: E402


@pytest.fixture
def wizard_env(monkeypatch, tmp_path):
    monkeypatch.setenv('SESSION_ID', 'sess-1')
    monkeypatch.setenv('USECASE_ID', 'uc-1')
    monkeypatch.setenv('WIZARD_QUEUE_URL', 'https://sqs/wizard')
    monkeypatch.setenv('S3_BUCKET', 'bucket')
    monkeypatch.setenv('DYNAMODB_TABLE_NAME', 'table')
    monkeypatch.setenv('LOGS_DIRECTORY', str(tmp_path))
    monkeypatch.setenv('USE_NOVA_ACT_GA', 'false')
    monkeypatch.setenv('EXTENSION_S3_PREFIX', '')  # no recorder extension
    monkeypatch.setenv('NOVA_ACT_API_KEY_NAME', 'nova-key')


def _run_main_with_sigterm_during(raise_from: str):
    """Run ``main()`` with every collaborator faked; ``raise_from`` names the
    db_client method that raises ``SystemExit(143)`` (the signal arriving)."""
    db_client = MagicMock(name='db_client')
    execution = MagicMock(status='running', starting_url='https://example.test/', created_at='2026-01-01T00:00:00Z',
                          region='eu-central-1')
    db_client.get_execution.return_value = execution
    db_client.get_execution_variables.return_value = None
    db_client.get_execution_headers.return_value = None
    getattr(db_client, raise_from).side_effect = SystemExit(143)

    secrets = MagicMock()
    secrets._get_secret_value_by_name.return_value = 'nova-api-key'
    template_parser = MagicMock()
    template_parser.get_all_variables.return_value = {'UniqueID': 'unique-1'}
    browser = MagicMock(name='browser')
    browser.generate_ws_headers.return_value = ('wss://cdp', {'h': 'v'})
    browser.generate_live_view_url.return_value = 'https://live'
    nova = MagicMock(name='nova')
    nova.get_session_id.return_value = 'nova-sess'
    nova_cls = MagicMock(name='NovaAct')
    nova_cls.return_value.__enter__.return_value = nova
    nova_cls.return_value.__exit__.return_value = False

    with patch.object(wizard_worker, 'install_sigterm_exit') as install, \
            patch.object(wizard_worker, 'DynamoDBClient', return_value=db_client), \
            patch.object(wizard_worker, 'SecretsClient', return_value=secrets), \
            patch.object(wizard_worker, 'TemplateParser', return_value=template_parser), \
            patch.object(wizard_worker, 'S3Writer'), \
            patch.object(wizard_worker, 'boto3'), \
            patch.object(wizard_worker, 'create_browser', return_value='browser-1') as create_browser, \
            patch.object(wizard_worker, 'start_browser', return_value=browser), \
            patch.object(wizard_worker, 'delete_browser') as delete_browser, \
            patch.object(wizard_worker, 'NovaAct', nova_cls), \
            pytest.raises(SystemExit) as raised:
        wizard_worker.main()

    return {
        'exit_code': raised.value.code,
        'install': install,
        'db_client': db_client,
        'create_browser': create_browser,
        'delete_browser': delete_browser,
        'browser': browser,
        'nova': nova,
        'nova_cls': nova_cls,
    }


def test_main_installs_the_handler_first(wizard_env):
    r = _run_main_with_sigterm_during('update_execution_status')
    r['install'].assert_called_once_with(wizard_worker.logger)
    # the very first status write raised, so nothing else ran
    r['create_browser'].assert_not_called()


def test_sigterm_in_the_command_loop_runs_the_final_cleanup_and_writes_no_failed(wizard_env):
    r = _run_main_with_sigterm_during('poll_wizard_commands')

    assert r['exit_code'] == 143
    statuses = [c.args[2] for c in r['db_client'].update_execution_status.call_args_list]
    assert statuses == ['running'], statuses  # neither ``failed`` nor ``timeout`` nor ``success``
    # the ``finally`` block ran: browser torn down, live view removed
    r['nova_cls'].return_value.__exit__.assert_called_once()
    r['browser'].stop.assert_called_once()
    r['delete_browser'].assert_called_once_with('browser-1', 'eu-central-1')
    r['db_client'].delete_live_view.assert_called_once_with('sess-1')


def test_sigterm_outside_the_command_loop_also_runs_the_final_cleanup(wizard_env):
    # the signal lands between browser creation and the loop (create_live_view)
    r = _run_main_with_sigterm_during('create_live_view')

    assert r['exit_code'] == 143
    statuses = [c.args[2] for c in r['db_client'].update_execution_status.call_args_list]
    assert statuses == ['running']
    r['browser'].stop.assert_called_once()
    r['delete_browser'].assert_called_once_with('browser-1', 'eu-central-1')
    r['db_client'].delete_live_view.assert_called_once_with('sess-1')
    r['nova_cls'].assert_not_called()


def test_an_ordinary_exception_still_writes_failed(wizard_env):
    """Control: the ``except Exception`` block is intact for real failures."""
    db_client = MagicMock(name='db_client')
    db_client.get_execution.side_effect = RuntimeError('ddb down')
    with patch.object(wizard_worker, 'install_sigterm_exit'), \
            patch.object(wizard_worker, 'DynamoDBClient', return_value=db_client), \
            patch.object(wizard_worker, 'SecretsClient'), \
            patch.object(wizard_worker, 'boto3'):
        assert wizard_worker.main() is False
    statuses = [c.args[2] for c in db_client.update_execution_status.call_args_list]
    assert statuses == ['running', 'failed']
