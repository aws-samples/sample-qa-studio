"""Tests for the MicroVM supervisor (``supervisor.py`` + ``supervisor_models.py``).

The child process, ``os.killpg`` and the ``lambda-microvms`` client are faked;
the HTTP hooks are exercised through a real ``ThreadingHTTPServer`` on an
ephemeral loopback port so the routing code is covered end to end.
"""
from __future__ import annotations

import http.client
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import supervisor  # noqa: E402
import supervisor_models  # noqa: E402
from supervisor import (  # noqa: E402
    Supervisor,
    SupervisorConfigError,
    SupervisorTiming,
    build_batch_command,
    build_batch_env,
    build_wizard_command,
    build_wizard_env,
    make_server,
    mask_env,
    parse_run_hook_body,
    resolve_credentials,
    soft_timeout_seconds,
    terminate_microvm,
)
from supervisor_models import (  # noqa: E402
    RUN_HOOK_PAYLOAD_MAX_BYTES,
    MobileConfig,
    PayloadTooLargeError,
    RunPayload,
)

# ── fixtures ────────────────────────────────────────────────────────

IMAGE_ENV = {
    "AWS_REGION": "eu-central-1",
    "DYNAMODB_TABLE_NAME": "qa-table",
    "S3_BUCKET_PREFIX": "qa-bucket",
    "SECRETS_PREFIX": "qa-secrets",
    "NOVA_ACT_API_KEY_NAME": "nova-key",
    "BEDROCK_EXECUTION_ROLE": "arn:aws:iam::123:role/bedrock",
    "USER_AGENT": "image-agent/1.0",
    "QA_STUDIO_API_URL_SSM": "/qa/api-url",
    "QA_STUDIO_TOKEN_ENDPOINT_SSM": "/qa/token-endpoint",
    "WORKER_CREDENTIALS_SECRET_ARN": "arn:aws:secretsmanager:eu-central-1:123:secret:worker",
    "WIZARD_QUEUE_URL": "https://sqs/wizard",
    "PATH": "/app/.venv/bin:/usr/bin",
    "PYTHONPATH": "/app",
}

CREDENTIALS = {
    "QA_STUDIO_API_URL": "https://api.example.com",
    "OAUTH_TOKEN_ENDPOINT": "https://auth.example.com/oauth2/token",
    "OAUTH_CLIENT_ID": "client-id",
    "OAUTH_CLIENT_SECRET": "client-secret-value",
}

MOBILE = {
    "test_platform": "mobile",
    "platform": "ANDROID",
    "app_package": "com.example.app",
    "app_activity": ".MainActivity",
    "app_binary_s3_path": "s3://bucket/app.apk",
    "device_farm_project_arn": "arn:aws:devicefarm:us-west-2:123:project:p",
    "device_arn": "arn:aws:devicefarm:us-west-2::device:d",
}


def batch_payload(**overrides) -> RunPayload:
    data = {
        "mode": "batch",
        "usecase_id": "uc-1",
        "execution_id": "ex-1",
        "execution_token": "tok-secret",
        "region": "eu-central-1",
        "s3_bucket": "qa-bucket-eu-central-1",
        "max_duration_s": 3600,
    }
    data.update(overrides)
    return RunPayload.model_validate(data)


def wizard_payload(**overrides) -> RunPayload:
    data = {
        "mode": "wizard",
        "usecase_id": "uc-1",
        "session_id": "sess-1",
        "region": "eu-central-1",
        "s3_bucket": "qa-bucket-eu-central-1",
        "max_duration_s": 14400,
    }
    data.update(overrides)
    return RunPayload.model_validate(data)


def run_body(payload: RunPayload, microvm_id: str | None = "vm-1") -> bytes:
    body = {"runHookPayload": payload.to_hook_payload()}
    if microvm_id is not None:
        body["microvmId"] = microvm_id
    return json.dumps(body).encode()


class FakeChild:
    """Stands in for ``subprocess.Popen``: exits when told to."""

    def __init__(self, pid: int = 4242):
        self.pid = pid
        self.returncode: int | None = None
        self._done = threading.Event()

    def exit(self, code: int) -> None:
        self.returncode = code
        self._done.set()

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if not self._done.wait(timeout):
            raise subprocess.TimeoutExpired("fake", timeout)
        return self.returncode


class Harness:
    """Wires a Supervisor to fakes and records every side effect."""

    def __init__(self, image_env=None, *, ignore_sigterm=False, timing=None):
        self.child = FakeChild()
        self.spawns: list[dict] = []
        self.signals: list[tuple[int, int]] = []
        self.terminated: list[str | None] = []
        self.ignore_sigterm = ignore_sigterm

        def popen(cmd, **kwargs):
            self.spawns.append({"cmd": cmd, **kwargs})
            return self.child

        def killpg(pgid, sig):
            self.signals.append((pgid, sig))
            if sig == signal.SIGKILL:
                self.child.exit(-9)
            elif sig == signal.SIGTERM and not self.ignore_sigterm:
                self.child.exit(143)

        def terminate(microvm_id):
            self.terminated.append(microvm_id)
            return True

        self.supervisor = Supervisor(
            image_env=dict(IMAGE_ENV if image_env is None else image_env),
            popen=popen,
            killpg=killpg,
            terminate=terminate,
            credentials_resolver=lambda env: dict(CREDENTIALS),
            timing=timing or SupervisorTiming(soft_grace_s=180, sigkill_grace_s=0.2, terminate_wait_s=0.5),
        )

    def wait_terminated(self, timeout=3.0) -> None:
        deadline = time.monotonic() + timeout
        while not self.terminated and time.monotonic() < deadline:
            time.sleep(0.01)
        assert self.terminated, "supervisor never self-terminated"


# ── supervisor_models ───────────────────────────────────────────────


class TestRunPayload:
    def test_batch_round_trip_keeps_token(self):
        payload = batch_payload()
        raw = payload.to_hook_payload()
        assert "tok-secret" in raw
        assert "\n" not in raw and ": " not in raw  # compact JSON
        restored = RunPayload.from_hook_payload(raw)
        assert restored.execution_token.get_secret_value() == "tok-secret"
        assert restored == payload

    def test_repr_and_dump_mask_token(self):
        payload = batch_payload()
        assert "tok-secret" not in repr(payload)
        assert "tok-secret" not in str(payload)
        assert "tok-secret" not in payload.model_dump_json()

    def test_batch_requires_execution_id_and_token(self):
        with pytest.raises(ValidationError, match="execution_id"):
            batch_payload(execution_id=None)
        with pytest.raises(ValidationError, match="execution_token"):
            batch_payload(execution_token=None)

    def test_wizard_requires_session_id(self):
        with pytest.raises(ValidationError, match="session_id"):
            wizard_payload(session_id=None)
        assert wizard_payload().run_id == "sess-1"
        assert batch_payload().run_id == "ex-1"

    def test_unknown_mode_and_extra_keys_rejected(self):
        with pytest.raises(ValidationError):
            batch_payload(mode="interactive")
        with pytest.raises(ValidationError):
            batch_payload(unexpected="x")

    def test_max_duration_bounds(self):
        with pytest.raises(ValidationError):
            batch_payload(max_duration_s=0)
        with pytest.raises(ValidationError):
            batch_payload(max_duration_s=28801)
        assert batch_payload(max_duration_s=28800).max_duration_s == 28800

    def test_too_large_payload_rejected_both_ways(self):
        payload = batch_payload(user_agent="x" * RUN_HOOK_PAYLOAD_MAX_BYTES)
        with pytest.raises(PayloadTooLargeError, match=str(RUN_HOOK_PAYLOAD_MAX_BYTES)):
            payload.to_hook_payload()
        raw = json.dumps({**json.loads(batch_payload().to_hook_payload()), "user_agent": "y" * 4100})
        with pytest.raises(PayloadTooLargeError):
            RunPayload.from_hook_payload(raw)

    def test_mobile_round_trip(self):
        payload = batch_payload(mobile=MOBILE)
        restored = RunPayload.from_hook_payload(payload.to_hook_payload())
        assert restored.mobile == MobileConfig.model_validate(MOBILE)

    def test_mobile_env_upper_cases_non_empty_fields_only(self):
        env = MobileConfig.model_validate({**MOBILE, "bundle_id": ""}).to_env()
        assert env == {
            "TEST_PLATFORM": "mobile",
            "PLATFORM": "ANDROID",
            "APP_PACKAGE": "com.example.app",
            "APP_ACTIVITY": ".MainActivity",
            "APP_BINARY_S3_PATH": "s3://bucket/app.apk",
            "DEVICE_FARM_PROJECT_ARN": MOBILE["device_farm_project_arn"],
            "DEVICE_ARN": MOBILE["device_arn"],
        }

    def test_models_module_is_dependency_light(self):
        import ast

        tree = ast.parse(Path(supervisor_models.__file__).read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert imported <= {"__future__", "json", "typing", "pydantic"}, imported


# ── pure helpers ────────────────────────────────────────────────────


class TestParseRunHookBody:
    def test_parses_microvm_id_and_payload(self):
        raw = json.dumps({"microvmId": "vm-9", "runHookPayload": '{"a":1}'}).encode()
        assert parse_run_hook_body(raw) == ("vm-9", '{"a":1}')

    def test_tolerates_missing_microvm_id(self, caplog):
        raw = json.dumps({"runHookPayload": "{}"}).encode()
        with caplog.at_level("WARNING", logger="supervisor"):
            assert parse_run_hook_body(raw) == (None, "{}")
        assert "microvmId" in caplog.text

    @pytest.mark.parametrize("raw", [b"not json", b"[]", b'{"microvmId":"x"}', b'{"runHookPayload": 5}'])
    def test_rejects_bad_bodies(self, raw):
        with pytest.raises(ValueError):
            parse_run_hook_body(raw)


class TestMaskEnv:
    def test_masks_secrets_and_keeps_rest(self):
        env = {"OAUTH_CLIENT_SECRET": "s", "QA_STUDIO_EXECUTION_TOKEN": "uc:ex:t", "AWS_REGION": "r"}
        masked = mask_env(env)
        assert masked == {"OAUTH_CLIENT_SECRET": "***", "QA_STUDIO_EXECUTION_TOKEN": "***", "AWS_REGION": "r"}
        assert env["OAUTH_CLIENT_SECRET"] == "s"  # input untouched


class TestSoftTimeout:
    @pytest.mark.parametrize("max_s,grace,expected", [(3600, 180, 3420), (180, 180, 0), (60, 180, 0)])
    def test_never_negative(self, max_s, grace, expected):
        assert soft_timeout_seconds(max_s, grace) == expected


# ── env + command construction ──────────────────────────────────────


class TestBatchEnv:
    def test_reproduces_ecs_contract(self):
        env = build_batch_env(batch_payload(), IMAGE_ENV, CREDENTIALS)
        assert env["AWS_REGION"] == "eu-central-1"
        assert env["EXECUTION_ID"] == "ex-1"
        assert env["USECASE_ID"] == "uc-1"
        assert env["DYNAMODB_TABLE_NAME"] == "qa-table"
        assert env["S3_BUCKET"] == "qa-bucket-eu-central-1"
        assert env["S3_BUCKET_PREFIX"] == "qa-bucket"
        assert env["USER_AGENT"] == "image-agent/1.0"
        assert env["BEDROCK_EXECUTION_ROLE"] == IMAGE_ENV["BEDROCK_EXECUTION_ROLE"]
        assert env["NOVA_ACT_API_KEY_NAME"] == "nova-key"
        assert env["SECRETS_PREFIX"] == "qa-secrets"
        assert env["QA_STUDIO_EXECUTION_TOKEN"] == "uc-1:ex-1:tok-secret"
        assert "EXECUTION_TOKEN" not in env
        assert env["QA_STUDIO_API_URL"] == CREDENTIALS["QA_STUDIO_API_URL"]
        assert env["OAUTH_TOKEN_ENDPOINT"] == CREDENTIALS["OAUTH_TOKEN_ENDPOINT"]
        assert env["OAUTH_CLIENT_ID"] == "client-id"
        assert env["OAUTH_CLIENT_SECRET"] == "client-secret-value"
        assert env["PATH"] == IMAGE_ENV["PATH"]  # image env passes through
        assert "DEVICE_FARM_REGION" not in env
        assert "TEST_PLATFORM" not in env

    def test_termination_reason_contract(self):
        env = build_batch_env(batch_payload(max_duration_s=1234), IMAGE_ENV, CREDENTIALS)
        assert env["QA_STUDIO_TERMINATION_REASON"] == "timeout"
        assert env["QA_STUDIO_MAX_DURATION_SECONDS"] == "1234"

    def test_payload_user_agent_overrides_image(self):
        env = build_batch_env(batch_payload(user_agent="custom/2"), IMAGE_ENV, CREDENTIALS)
        assert env["USER_AGENT"] == "custom/2"

    def test_missing_user_agent_is_empty_like_today(self):
        image_env = {k: v for k, v in IMAGE_ENV.items() if k != "USER_AGENT"}
        assert build_batch_env(batch_payload(), image_env, CREDENTIALS)["USER_AGENT"] == ""

    def test_mobile_fields_exported_upper_case(self):
        env = build_batch_env(batch_payload(mobile=MOBILE), IMAGE_ENV, CREDENTIALS)
        assert env["DEVICE_FARM_REGION"] == "us-west-2"
        assert env["TEST_PLATFORM"] == "mobile"
        assert env["PLATFORM"] == "ANDROID"
        assert env["APP_PACKAGE"] == "com.example.app"
        assert env["DEVICE_ARN"] == MOBILE["device_arn"]
        assert "BUNDLE_ID" not in env

    def test_image_device_farm_region_wins(self):
        env = build_batch_env(batch_payload(mobile=MOBILE), {**IMAGE_ENV, "DEVICE_FARM_REGION": "us-east-1"}, CREDENTIALS)
        assert env["DEVICE_FARM_REGION"] == "us-east-1"

    @pytest.mark.parametrize("missing", supervisor.BATCH_REQUIRED_IMAGE_ENV)
    def test_missing_image_env_is_a_config_error(self, missing):
        image_env = {k: v for k, v in IMAGE_ENV.items() if k != missing}
        with pytest.raises(SupervisorConfigError, match=missing):
            build_batch_env(batch_payload(), image_env, CREDENTIALS)

    def test_command_line_matches_entrypoint(self):
        assert build_batch_command(batch_payload(), IMAGE_ENV) == [
            "qa-studio", "run",
            "--usecase-id", "uc-1",
            "--execution-id", "ex-1",
            "--browser", "agentcore",
            "--format", "json",
            "--verbose",
            "--region", "eu-central-1",
        ]


class TestWizardEnv:
    def test_reproduces_start_wizard_session_contract(self):
        env = build_wizard_env(wizard_payload(), IMAGE_ENV)
        assert "WORKER_MODE" not in env  # entrypoint.sh is gone; nothing reads it
        assert env["SESSION_ID"] == "sess-1"
        assert env["USECASE_ID"] == "uc-1"
        assert env["WIZARD_QUEUE_URL"] == "https://sqs/wizard"
        assert env["DYNAMODB_TABLE_NAME"] == "qa-table"
        assert env["S3_BUCKET"] == "qa-bucket-eu-central-1"
        assert env["BEDROCK_EXECUTION_ROLE"] == IMAGE_ENV["BEDROCK_EXECUTION_ROLE"]
        assert env["NOVA_ACT_API_KEY_NAME"] == "nova-key"
        assert "OAUTH_CLIENT_SECRET" not in env
        assert "QA_STUDIO_TERMINATION_REASON" not in env

    @pytest.mark.parametrize("missing", supervisor.WIZARD_REQUIRED_IMAGE_ENV)
    def test_missing_image_env_is_a_config_error(self, missing):
        image_env = {k: v for k, v in IMAGE_ENV.items() if k != missing}
        with pytest.raises(SupervisorConfigError, match=missing):
            build_wizard_env(wizard_payload(), image_env)

    def test_command(self):
        assert build_wizard_command() == ["python", "wizard_worker.py"]


# ── AWS helpers (fake clients) ──────────────────────────────────────


class TestEnsureDefaultRegion:
    """The platform injects AWS_REGION only; botocore resolves the region from AWS_DEFAULT_REGION."""

    def test_copies_aws_region_when_default_is_missing(self):
        env = {"AWS_REGION": "eu-central-1"}
        assert supervisor.ensure_default_region(env) == "eu-central-1"
        assert env["AWS_DEFAULT_REGION"] == "eu-central-1"

    def test_keeps_an_existing_default(self):
        env = {"AWS_REGION": "eu-central-1", "AWS_DEFAULT_REGION": "us-east-1"}
        assert supervisor.ensure_default_region(env) == "us-east-1"
        assert env["AWS_DEFAULT_REGION"] == "us-east-1"

    def test_no_region_at_all_is_left_alone(self):
        env: dict[str, str] = {}
        assert supervisor.ensure_default_region(env) is None
        assert "AWS_DEFAULT_REGION" not in env

    def test_batch_and_wizard_children_get_it(self):
        image_env = {k: v for k, v in IMAGE_ENV.items() if k != "AWS_DEFAULT_REGION"}
        assert build_batch_env(batch_payload(), image_env, CREDENTIALS)["AWS_DEFAULT_REGION"] == "eu-central-1"
        assert build_wizard_env(wizard_payload(), image_env)["AWS_DEFAULT_REGION"] == "eu-central-1"

    def test_run_hook_sets_it_on_the_process_before_creating_clients(self, monkeypatch):
        monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
        monkeypatch.setenv("AWS_REGION", "eu-central-1")
        seen = {}
        harness = Harness(image_env={k: v for k, v in IMAGE_ENV.items() if k != "AWS_DEFAULT_REGION"})

        def resolver(image_env):
            seen["default_region"] = os.environ.get("AWS_DEFAULT_REGION")
            return dict(CREDENTIALS)

        harness.supervisor._resolve_credentials = resolver
        status, _ = harness.supervisor.run(run_body(batch_payload()))
        assert status == 200
        assert seen["default_region"] == "eu-central-1"
        assert harness.spawns[0]["env"]["AWS_DEFAULT_REGION"] == "eu-central-1"


class TestResolveCredentials:
    class FakeSSM:
        def __init__(self):
            self.values = {"/qa/api-url": "https://api", "/qa/token-endpoint": "https://token"}
            self.calls = []

        def get_parameter(self, Name):
            self.calls.append(Name)
            return {"Parameter": {"Value": self.values[Name]}}

    class FakeSecrets:
        def __init__(self, secret):
            self.secret = secret
            self.calls = []

        def get_secret_value(self, SecretId):
            self.calls.append(SecretId)
            return {"SecretString": self.secret}

    def test_reads_ssm_and_secret(self):
        ssm = self.FakeSSM()
        secrets = self.FakeSecrets(json.dumps({"client_id": "cid", "client_secret": "csec"}))
        creds = resolve_credentials(IMAGE_ENV, ssm=ssm, secretsmanager=secrets)
        assert creds == {
            "QA_STUDIO_API_URL": "https://api",
            "OAUTH_TOKEN_ENDPOINT": "https://token",
            "OAUTH_CLIENT_ID": "cid",
            "OAUTH_CLIENT_SECRET": "csec",
        }
        assert ssm.calls == ["/qa/api-url", "/qa/token-endpoint"]
        assert secrets.calls == [IMAGE_ENV["WORKER_CREDENTIALS_SECRET_ARN"]]

    def test_malformed_secret_is_a_config_error(self):
        secrets = self.FakeSecrets(json.dumps({"client_id": "cid"}))
        with pytest.raises(SupervisorConfigError, match="client_secret"):
            resolve_credentials(IMAGE_ENV, ssm=self.FakeSSM(), secretsmanager=secrets)

    def test_missing_ssm_name_is_a_config_error(self):
        image_env = {k: v for k, v in IMAGE_ENV.items() if k != "QA_STUDIO_API_URL_SSM"}
        with pytest.raises(SupervisorConfigError, match="QA_STUDIO_API_URL_SSM"):
            resolve_credentials(image_env, ssm=self.FakeSSM(), secretsmanager=self.FakeSecrets("{}"))

    def test_aws_errors_become_config_errors(self):
        from botocore.exceptions import ClientError

        class DeniedSSM:
            def get_parameter(self, Name):
                raise ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "GetParameter")

        with pytest.raises(SupervisorConfigError, match="/qa/api-url.*AccessDenied"):
            resolve_credentials(IMAGE_ENV, ssm=DeniedSSM(), secretsmanager=self.FakeSecrets("{}"))

        class DeniedSecrets:
            def get_secret_value(self, SecretId):
                raise ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "GetSecretValue")

        with pytest.raises(SupervisorConfigError, match="Secrets Manager read failed"):
            resolve_credentials(IMAGE_ENV, ssm=self.FakeSSM(), secretsmanager=DeniedSecrets())


class TestTerminateMicrovm:
    class FakeClient:
        def __init__(self, error=None):
            self.calls = []
            self.error = error

        def terminate_microvm(self, **kwargs):
            self.calls.append(kwargs)
            if self.error:
                raise self.error

    def test_client_creation_failure_is_logged_not_raised(self, monkeypatch, caplog):
        """botocore without the lambda-microvms model (or no region) must not crash the reaper."""
        from botocore.exceptions import UnknownServiceError

        def boom(name, **kwargs):
            raise UnknownServiceError(service_name=name, known_service_names="ssm")

        monkeypatch.setattr(supervisor.boto3, "client", boom)
        with caplog.at_level("ERROR", logger="supervisor"):
            assert terminate_microvm("vm-1") is False
        assert "lambda-microvms" in caplog.text

    def test_calls_api_with_identifier(self):
        client = self.FakeClient()
        assert terminate_microvm("vm-1", client=client) is True
        assert client.calls == [{"microvmIdentifier": "vm-1"}]

    def test_falls_back_to_env_and_logs_when_absent(self, caplog):
        client = self.FakeClient()
        assert terminate_microvm(None, client=client, environ={"MICROVM_ID": "vm-env"}) is True
        assert client.calls == [{"microvmIdentifier": "vm-env"}]
        with caplog.at_level("ERROR", logger="supervisor"):
            assert terminate_microvm(None, client=client, environ={}) is False
        assert "microvmId" in caplog.text
        assert len(client.calls) == 1

    def test_api_error_is_logged_not_raised(self, caplog):
        from botocore.exceptions import ClientError, EndpointConnectionError

        err = ClientError({"Error": {"Code": "ResourceNotFoundException", "Message": "gone"}}, "TerminateMicrovm")
        with caplog.at_level("ERROR", logger="supervisor"):
            assert terminate_microvm("vm-1", client=self.FakeClient(error=err)) is False
            assert terminate_microvm("vm-1", client=self.FakeClient(error=EndpointConnectionError(endpoint_url="x"))) is False
        assert "ResourceNotFoundException" in caplog.text


# ── Supervisor lifecycle ────────────────────────────────────────────


class TestSupervisorRun:
    def test_batch_run_spawns_child_in_new_session(self):
        h = Harness()
        status, body = h.supervisor.run(run_body(batch_payload()))
        assert status == 200, body
        assert body == {"status": "started", "mode": "batch", "execution_id": "ex-1"}
        spawn = h.spawns[0]
        assert spawn["cmd"][:2] == ["qa-studio", "run"]
        assert spawn["start_new_session"] is True
        assert spawn["cwd"] == "/app"
        assert spawn["env"]["QA_STUDIO_EXECUTION_TOKEN"] == "uc-1:ex-1:tok-secret"
        assert spawn["env"]["QA_STUDIO_TERMINATION_REASON"] == "timeout"
        h.child.exit(0)
        h.wait_terminated()
        assert h.terminated == ["vm-1"]

    def test_wizard_run(self):
        h = Harness()
        status, body = h.supervisor.run(run_body(wizard_payload()))
        assert status == 200, body
        assert body["mode"] == "wizard" and body["execution_id"] == "sess-1"
        assert h.spawns[0]["cmd"] == ["python", "wizard_worker.py"]
        assert h.spawns[0]["env"]["SESSION_ID"] == "sess-1"
        h.child.exit(0)
        h.wait_terminated()

    def test_exit_logged_as_json_line_and_self_terminates(self, caplog):
        h = Harness()
        with caplog.at_level("INFO", logger="supervisor"):
            h.supervisor.run(run_body(batch_payload()))
            h.child.exit(3)
            h.wait_terminated()
        line = next(r.message for r in caplog.records if r.message.startswith("{") and '"exit_code"' in r.message)
        record = json.loads(line)
        assert record["execution_id"] == "ex-1"
        assert record["exit_code"] == 3
        assert record["duration_s"] >= 0
        assert record["microvm_id"] == "vm-1"
        assert "tok-secret" not in caplog.text
        assert "client-secret-value" not in caplog.text

    def test_invalid_payload_returns_400_and_terminates(self, caplog):
        h = Harness()
        raw = json.dumps({"microvmId": "vm-bad", "runHookPayload": json.dumps({"mode": "batch"})}).encode()
        with caplog.at_level("ERROR", logger="supervisor"):
            status, body = h.supervisor.run(raw)
        assert status == 400
        assert "usecase_id" in body["error"]
        assert "usecase_id" in caplog.text
        assert h.spawns == []
        assert h.terminated == ["vm-bad"]

    def test_unparsable_body_returns_400(self):
        h = Harness()
        status, body = h.supervisor.run(b"nope")
        assert status == 400
        assert h.terminated == [None]

    def test_oversized_payload_returns_400(self):
        h = Harness()
        raw = json.dumps({"microvmId": "vm-1", "runHookPayload": "x" * 5000}).encode()
        status, body = h.supervisor.run(raw)
        assert status == 400
        assert str(RUN_HOOK_PAYLOAD_MAX_BYTES) in body["error"]

    def test_second_run_is_409(self):
        h = Harness()
        assert h.supervisor.run(run_body(batch_payload()))[0] == 200
        status, body = h.supervisor.run(run_body(batch_payload(execution_id="ex-2")))
        assert status == 409
        assert len(h.spawns) == 1
        h.child.exit(0)
        h.wait_terminated()

    def test_missing_image_env_returns_500_and_terminates(self):
        h = Harness(image_env={k: v for k, v in IMAGE_ENV.items() if k != "SECRETS_PREFIX"})
        status, body = h.supervisor.run(run_body(batch_payload()))
        assert status == 500
        assert "SECRETS_PREFIX" in body["error"]
        assert h.terminated == ["vm-1"]
        assert h.spawns == []

    def test_credential_resolution_failure_returns_500(self):
        h = Harness()

        def boom(env):
            raise SupervisorConfigError("SSM get_parameter failed for /qa/api-url: AccessDenied")

        h.supervisor._resolve_credentials = boom
        status, body = h.supervisor.run(run_body(batch_payload()))
        assert status == 500
        assert "AccessDenied" in body["error"]
        assert h.terminated == ["vm-1"]

    def test_spawn_failure_returns_500(self):
        h = Harness()

        def failing_popen(cmd, **kwargs):
            raise FileNotFoundError("qa-studio")

        h.supervisor._popen = failing_popen
        status, body = h.supervisor.run(run_body(batch_payload()))
        assert status == 500
        assert "qa-studio" in body["error"]
        assert h.terminated == ["vm-1"]

    def test_run_returns_before_child_exits(self):
        h = Harness()
        started = time.monotonic()
        status, _ = h.supervisor.run(run_body(batch_payload()))
        assert status == 200
        assert time.monotonic() - started < 2.0
        assert h.child.returncode is None
        h.child.exit(0)
        h.wait_terminated()


class TestWatchdog:
    def test_soft_timeout_sigterms_group(self):
        timing = SupervisorTiming(soft_grace_s=1, sigkill_grace_s=0.2, terminate_wait_s=0.5)
        h = Harness(timing=timing)
        h.supervisor.run(run_body(batch_payload(max_duration_s=1)))  # delay 0 → fires now
        h.wait_terminated()
        assert h.signals == [(h.child.pid, signal.SIGTERM)]
        assert h.child.returncode == 143

    def test_sigkill_after_grace_when_child_ignores_sigterm(self):
        timing = SupervisorTiming(soft_grace_s=1, sigkill_grace_s=0.1, terminate_wait_s=0.5)
        h = Harness(timing=timing, ignore_sigterm=True)
        h.supervisor.run(run_body(batch_payload(max_duration_s=1)))
        h.wait_terminated()
        assert h.signals == [(h.child.pid, signal.SIGTERM), (h.child.pid, signal.SIGKILL)]
        assert h.child.returncode == -9

    def test_watchdog_does_not_fire_after_normal_exit(self):
        timing = SupervisorTiming(soft_grace_s=1, sigkill_grace_s=0.1, terminate_wait_s=0.5)
        h = Harness(timing=timing)
        h.supervisor.run(run_body(batch_payload(max_duration_s=2)))  # delay 1 s
        h.child.exit(0)
        h.wait_terminated()
        time.sleep(1.2)
        assert h.signals == []

    def test_process_lookup_error_is_tolerated(self):
        timing = SupervisorTiming(soft_grace_s=1, sigkill_grace_s=0.1, terminate_wait_s=0.5)
        h = Harness(timing=timing)

        def killpg(pgid, sig):
            h.child.exit(0)
            raise ProcessLookupError

        h.supervisor._killpg = killpg
        h.supervisor.run(run_body(batch_payload(max_duration_s=1)))
        h.wait_terminated()


class TestTerminateHook:
    def test_sigterms_child_and_waits(self):
        h = Harness()
        h.supervisor.run(run_body(batch_payload()))
        status, body = h.supervisor.terminate_hook()
        assert status == 200
        assert body["child_exit_code"] == 143
        assert h.signals == [(h.child.pid, signal.SIGTERM)]
        # The platform is already terminating us: no TerminateMicrovm round trip.
        time.sleep(0.1)
        assert h.terminated == []

    def test_sigkills_when_child_outlives_wait(self):
        timing = SupervisorTiming(soft_grace_s=180, sigkill_grace_s=0.1, terminate_wait_s=0.1)
        h = Harness(timing=timing, ignore_sigterm=True)
        h.supervisor.run(run_body(batch_payload()))
        status, body = h.supervisor.terminate_hook()
        assert status == 200
        assert h.signals == [(h.child.pid, signal.SIGTERM), (h.child.pid, signal.SIGKILL)]

    def test_without_child_is_a_noop_200(self):
        h = Harness()
        assert h.supervisor.terminate_hook() == (200, {"status": "terminated", "child_exit_code": None})
        assert h.signals == []


class TestHealth:
    def test_ready_when_cli_help_succeeds(self):
        calls = []

        def run(cmd, **kwargs):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="Usage: qa-studio [OPTIONS]\n", stderr="")

        sup = Supervisor(image_env={}, cli_run=run)
        assert sup.health() == (200, {"status": "ready", "qa_studio": "Usage: qa-studio [OPTIONS]"})
        assert calls == [list(supervisor.CLI_HEALTH_COMMAND)]
        # The installed CLI has no --version flag (exit 2); --help proves the
        # console script, venv shebang and import graph work.
        assert supervisor.CLI_HEALTH_COMMAND == ("qa-studio", "--help")

    def test_not_ready_when_cli_fails_or_missing(self):
        def failing(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")

        def missing(cmd, **kwargs):
            raise FileNotFoundError("qa-studio")

        assert Supervisor(image_env={}, cli_run=failing).health()[0] == 503
        assert Supervisor(image_env={}, cli_run=missing).health()[0] == 503


# ── HTTP hooks through a real server ────────────────────────────────


@pytest.fixture
def http_harness():
    h = Harness()
    server = make_server(h.supervisor, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield h, server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def post(port: int, hook: str, body: bytes = b"") -> tuple[int, dict]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", f"{supervisor.HOOK_PREFIX}{hook}", body=body, headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    data = json.loads(response.read() or b"{}")
    conn.close()
    return response.status, data


class TestHttpHooks:
    def test_suspend_and_resume_return_200(self, http_harness):
        _, port = http_harness
        assert post(port, "suspend") == (200, {"status": "ok", "hook": "suspend"})
        assert post(port, "resume") == (200, {"status": "ok", "hook": "resume"})

    def test_ready_and_validate_delegate_to_health(self, http_harness):
        h, port = http_harness
        h.supervisor._cli_run = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout="v", stderr="")
        assert post(port, "ready")[0] == 200
        assert post(port, "validate")[0] == 200

    def test_run_then_terminate(self, http_harness):
        h, port = http_harness
        status, body = post(port, "run", run_body(batch_payload()))
        assert status == 200 and body["execution_id"] == "ex-1"
        status, body = post(port, "terminate")
        assert status == 200 and body["child_exit_code"] == 143

    def test_run_rejects_bad_payload(self, http_harness):
        h, port = http_harness
        status, body = post(port, "run", b"garbage")
        assert status == 400 and "error" in body

    def test_unknown_hook_404_and_get_405(self, http_harness):
        _, port = http_harness
        assert post(port, "explode")[0] == 404
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", f"{supervisor.HOOK_PREFIX}ready")
        assert conn.getresponse().status == 405
        conn.request("POST", "/somewhere/else", body=b"")
        assert conn.getresponse().status == 404
        conn.close()

    def test_unexpected_exception_is_a_500_not_a_dropped_connection(self, http_harness, caplog):
        h, port = http_harness

        def explode(cmd, **kwargs):
            raise RuntimeError("unexpected")

        h.supervisor._cli_run = explode
        with caplog.at_level("ERROR", logger="supervisor"):
            status, body = post(port, "ready")
        assert status == 500
        assert body == {"error": "internal error handling ready"}
        assert "unexpected" in caplog.text


def test_main_serves_until_interrupted(monkeypatch, caplog):
    created = {}

    class FakeServer:
        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            created["closed"] = True

    def fake_make_server(sup, *, host, port):
        created.update(host=host, port=port, cwd=sup._cwd)
        return FakeServer()

    monkeypatch.setattr(supervisor, "make_server", fake_make_server)
    monkeypatch.setattr(supervisor.logging, "basicConfig", lambda **kwargs: None)
    assert supervisor.main(["--host", "127.0.0.1", "--port", "0", "--cwd", "/tmp/app"]) == 0
    assert created == {"host": "127.0.0.1", "port": 0, "cwd": "/tmp/app", "closed": True}


# ── import hygiene ──────────────────────────────────────────────────


def test_no_import_time_side_effects():
    """Snapshot cloning: importing the module must not create clients or sockets."""
    code = (
        "import sys, pathlib; sys.path.insert(0, sys.argv[1])\n"
        "import boto3, socket\n"
        "calls = []\n"
        "boto3.client = lambda *a, **k: calls.append(('boto3', a)) or None\n"
        "boto3.Session = lambda *a, **k: calls.append(('session', a)) or None\n"
        "orig_bind = socket.socket.bind\n"
        "socket.socket.bind = lambda self, *a: calls.append(('bind', a)) or orig_bind(self, *a)\n"
        "import supervisor, supervisor_models\n"
        "print(len(calls))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(Path(supervisor.__file__).parent)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0"
