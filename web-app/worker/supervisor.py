"""MicroVM supervisor: lifecycle hooks → one child process.

Lambda MicroVMs POST lifecycle hooks to ``:8080/aws/lambda-microvms/runtime/v1/<hook>``.
This process answers them and owns exactly one child per VM:

``/ready``, ``/validate``
    200 iff ``qa-studio --help`` exits 0 (image build time only).
``/run``
    Parse ``runHookPayload`` into :class:`supervisor_models.RunPayload`,
    resolve the API URL and token endpoint from SSM, fetch the M2M client
    credentials from Secrets Manager, spawn ``qa-studio run …`` (batch) or
    ``python wizard_worker.py`` (wizard) in its own process group, start the
    watchdog and return 200 at once — the platform allows ≤ 60 s, we aim for 2.
``/terminate``
    SIGTERM the child's group, wait up to :attr:`SupervisorTiming.terminate_wait_s`
    (≤ 30 s, the platform's ``terminateTimeoutInSeconds`` ceiling), 200.
``/suspend``, ``/resume``
    200.  Never expected: the launcher sets ``maxIdleDurationSeconds`` to the
    VM's maximum duration, but a misconfigured launch must not wedge.

Watchdog: ``max_duration_s - soft_grace_s`` after spawn the child's group gets
SIGTERM, then SIGKILL after ``sigkill_grace_s``.  When the child exits for any
reason the supervisor logs one JSON line and calls ``TerminateMicrovm`` on
itself.

Snapshot cloning: nothing below creates a boto3 client, random value or socket
at import time.  All per-run state is created inside ``/run``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess  # nosec B404 — spawning the runner child is this module's purpose; argv lists only, no shell
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Mapping, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from supervisor_models import PayloadTooLargeError, RunPayload

logger = logging.getLogger("supervisor")

HOOK_PREFIX = "/aws/lambda-microvms/runtime/v1/"
DEFAULT_PORT = 8080
DEFAULT_CWD = "/app"

#: Stack-constant env the image provides; checked before a batch child is spawned.
BATCH_REQUIRED_IMAGE_ENV = (
    "AWS_REGION",
    "DYNAMODB_TABLE_NAME",
    "S3_BUCKET_PREFIX",
    "SECRETS_PREFIX",
    "NOVA_ACT_API_KEY_NAME",
    "BEDROCK_EXECUTION_ROLE",
)
#: Stack-constant env the legacy wizard worker reads.
WIZARD_REQUIRED_IMAGE_ENV = (
    "WIZARD_QUEUE_URL",
    "DYNAMODB_TABLE_NAME",
    "BEDROCK_EXECUTION_ROLE",
    "NOVA_ACT_API_KEY_NAME",
)
#: Env the supervisor itself needs to mint the child's API credentials.
CREDENTIAL_IMAGE_ENV = (
    "QA_STUDIO_API_URL_SSM",
    "QA_STUDIO_TOKEN_ENDPOINT_SSM",
    "WORKER_CREDENTIALS_SECRET_ARN",
)
#: Never printed; see :func:`mask_env`.
SENSITIVE_ENV_KEYS = frozenset({"OAUTH_CLIENT_SECRET", "QA_STUDIO_EXECUTION_TOKEN"})

#: Today's hard-coded Device Farm region (``execute_usecase.py``); image env may override.
DEFAULT_DEVICE_FARM_REGION = "us-west-2"

#: ``/ready`` / ``/validate`` probe.  The installed CLI has no ``--version``
#: flag (click exits 2); ``--help`` exercises the console script, the venv
#: shebang and the import graph, which is what the image build must prove.
CLI_HEALTH_COMMAND = ("qa-studio", "--help")

Popen = Callable[..., Any]
Killpg = Callable[[int, int], None]
Terminate = Callable[[Optional[str]], bool]
CredentialsResolver = Callable[[Mapping[str, str]], dict[str, str]]
CliRun = Callable[..., subprocess.CompletedProcess]


class SupervisorConfigError(RuntimeError):
    """The image env or the AWS-side configuration is incomplete."""


class SupervisorTiming(BaseModel):
    """Watchdog and hook timing; tests shrink these."""

    model_config = ConfigDict(frozen=True)

    #: Seconds before ``max_duration_s`` at which the soft timeout fires.
    soft_grace_s: float = Field(default=180, ge=0)
    #: Seconds between SIGTERM and SIGKILL.
    sigkill_grace_s: float = Field(default=30, ge=0)
    #: Max seconds the ``/terminate`` hook blocks (platform ceiling: 60 s).
    terminate_wait_s: float = Field(default=30, ge=0, le=60)


def soft_timeout_seconds(max_duration_s: int, soft_grace_s: float) -> float:
    """Delay from spawn to the soft timeout; never negative (fires at once if the ceiling is tiny)."""
    return max(max_duration_s - soft_grace_s, 0)


# ── pure helpers ────────────────────────────────────────────────────


def parse_run_hook_body(raw: bytes) -> tuple[Optional[str], str]:
    """Split the ``/run`` body into ``(microvm_id, run_hook_payload)``.

    Accepts ``{"microvmId": str, "runHookPayload": str}``.  A missing
    ``microvmId`` is tolerated (logged) so self-termination can fall back to
    the ``MICROVM_ID`` env var; anything else raises ``ValueError``.
    """
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError(f"/run body is not JSON: {exc}") from exc
    if not isinstance(body, dict):
        raise ValueError("/run body must be a JSON object")
    payload = body.get("runHookPayload")
    if not isinstance(payload, str):
        raise ValueError("/run body must carry runHookPayload as a string")
    microvm_id = body.get("microvmId")
    if not isinstance(microvm_id, str) or not microvm_id:
        logger.warning("/run body carries no microvmId; self-terminate will fall back to MICROVM_ID env")
        microvm_id = None
    return microvm_id, payload


def mask_env(env: Mapping[str, str]) -> dict[str, str]:
    """Copy of ``env`` safe to log."""
    return {key: ("***" if key in SENSITIVE_ENV_KEYS else value) for key, value in env.items()}


def _require(env: Mapping[str, str], names: tuple[str, ...], purpose: str) -> None:
    missing = [name for name in names if not env.get(name)]
    if missing:
        raise SupervisorConfigError(f"image env for {purpose} is missing: {', '.join(missing)}")


def ensure_default_region(env: dict[str, str]) -> Optional[str]:
    """Make the region visible to botocore; returns the region in effect.

    The platform injects ``AWS_REGION`` (and rejects it as an image env key),
    but botocore reads only ``AWS_DEFAULT_REGION`` and raises ``NoRegionError``
    otherwise (seen on the first dev run).  Copy it when the default is absent.
    """
    region = env.get("AWS_DEFAULT_REGION") or env.get("AWS_REGION")
    if region and not env.get("AWS_DEFAULT_REGION"):
        env["AWS_DEFAULT_REGION"] = region
    return region or None


# ── AWS helpers (clients created lazily, never at import) ───────────


def resolve_credentials(
    image_env: Mapping[str, str],
    *,
    ssm: Any = None,
    secretsmanager: Any = None,
) -> dict[str, str]:
    """Mint the CLI's auth contract (``qa_studio_cli/auth/resolver.py``).

    Reads ``QA_STUDIO_API_URL`` and ``OAUTH_TOKEN_ENDPOINT`` from the SSM
    parameters named in the image env and ``{client_id, client_secret}`` from
    the Secrets Manager secret.  The secret value is never logged.
    """
    _require(image_env, CREDENTIAL_IMAGE_ENV, "credential resolution")
    ssm = ssm or boto3.client("ssm")
    secretsmanager = secretsmanager or boto3.client("secretsmanager")

    def parameter(name: str) -> str:
        try:
            return ssm.get_parameter(Name=name)["Parameter"]["Value"]
        except (BotoCoreError, ClientError) as exc:
            raise SupervisorConfigError(f"SSM get_parameter failed for {name}: {exc}") from exc

    api_url = parameter(image_env["QA_STUDIO_API_URL_SSM"])
    token_endpoint = parameter(image_env["QA_STUDIO_TOKEN_ENDPOINT_SSM"])

    secret_arn = image_env["WORKER_CREDENTIALS_SECRET_ARN"]
    try:
        secret_string = secretsmanager.get_secret_value(SecretId=secret_arn)["SecretString"]
        secret = json.loads(secret_string)
    except (BotoCoreError, ClientError, ValueError, KeyError) as exc:
        raise SupervisorConfigError(f"Secrets Manager read failed for {secret_arn}: {type(exc).__name__}") from exc
    if not isinstance(secret, dict) or not secret.get("client_id") or not secret.get("client_secret"):
        raise SupervisorConfigError(f"secret {secret_arn} must be JSON with client_id and client_secret")

    return {
        "QA_STUDIO_API_URL": api_url,
        "OAUTH_TOKEN_ENDPOINT": token_endpoint,
        "OAUTH_CLIENT_ID": str(secret["client_id"]),
        "OAUTH_CLIENT_SECRET": str(secret["client_secret"]),
    }


def terminate_microvm(
    microvm_id: Optional[str],
    *,
    client: Any = None,
    environ: Mapping[str, str] = os.environ,
) -> bool:
    """``lambda-microvms:TerminateMicrovm`` on ourselves. Logs failures, never raises."""
    microvm_id = microvm_id or environ.get("MICROVM_ID")
    if not microvm_id:
        logger.error("Cannot self-terminate: no microvmId in the /run body and MICROVM_ID is unset")
        return False
    try:
        client = client or boto3.client("lambda-microvms")
        client.terminate_microvm(microvmIdentifier=microvm_id)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "ClientError")
        logger.error("TerminateMicrovm(%s) failed: %s: %s", microvm_id, code, exc)
        return False
    except BotoCoreError as exc:
        # Includes UnknownServiceError (botocore < 1.43.35 has no lambda-microvms model) and NoRegionError.
        logger.error("TerminateMicrovm(%s) failed: lambda-microvms client: %s", microvm_id, exc)
        return False
    logger.info("TerminateMicrovm(%s) requested", microvm_id)
    return True


# ── env + command construction ──────────────────────────────────────


def build_batch_env(
    payload: RunPayload,
    image_env: Mapping[str, str],
    credentials: Mapping[str, str],
) -> dict[str, str]:
    """Child env for ``qa-studio run``.

    Per-execution values come from the payload (what ``execute_usecase.py``
    put into the ``RunPayload``), stack constants from the image env, which is
    passed through wholesale (``PATH``, ``PYTHONPATH``, Nova Act settings, …).
    """
    _require(image_env, BATCH_REQUIRED_IMAGE_ENV, "batch mode")
    if payload.mode != "batch" or payload.execution_token is None:
        raise SupervisorConfigError("build_batch_env needs a batch payload with an execution_token")
    execution_id = payload.run_id

    env = dict(image_env)
    ensure_default_region(env)
    env.update(credentials)
    env.update({
        "EXECUTION_ID": execution_id,
        "USECASE_ID": payload.usecase_id,
        "S3_BUCKET": payload.s3_bucket,
        "USER_AGENT": payload.user_agent if payload.user_agent is not None else image_env.get("USER_AGENT", ""),
        # Execution-bound worker capability (X-QA-Execution-Token). Never logged.
        "QA_STUDIO_EXECUTION_TOKEN": (
            f"{payload.usecase_id}:{execution_id}:{payload.execution_token.get_secret_value()}"
        ),
        # Termination contract of qa_studio_cli/runner/termination.py.  The
        # child reads these at SIGNAL time and we cannot change a running
        # child's env, so the reason is fixed at spawn.  In the MicroVM there
        # are only two SIGTERM sources: (a) our watchdog soft timeout and (b)
        # the /terminate hook.  (b) is reached either by the platform's
        # maximumDurationInSeconds kill (a timeout too) or by stop_execution,
        # which writes the terminal `stopped` status *before* calling
        # TerminateMicrovm — the server rejects the runner's late `failed`
        # PATCH.  A SIGTERM that reaches the status record is therefore, by
        # construction, a timeout.
        "QA_STUDIO_TERMINATION_REASON": "timeout",
        "QA_STUDIO_MAX_DURATION_SECONDS": str(payload.max_duration_s),
    })
    env.pop("EXECUTION_TOKEN", None)

    if payload.mobile is not None:
        env["DEVICE_FARM_REGION"] = image_env.get("DEVICE_FARM_REGION") or DEFAULT_DEVICE_FARM_REGION
        env.update(payload.mobile.to_env())
    return env


def build_batch_command(payload: RunPayload, image_env: Mapping[str, str]) -> list[str]:
    """Command line for the batch child (always ``--verbose``: the VM console is the log stream)."""
    return [
        "qa-studio", "run",
        "--usecase-id", payload.usecase_id,
        "--execution-id", payload.run_id,
        "--browser", "agentcore",
        "--format", "json",
        "--verbose",
        "--region", image_env["AWS_REGION"],
    ]


def build_wizard_env(payload: RunPayload, image_env: Mapping[str, str]) -> dict[str, str]:
    """Child env for the legacy ``wizard_worker.py`` (mirrors ``start_wizard_session.py``)."""
    _require(image_env, WIZARD_REQUIRED_IMAGE_ENV, "wizard mode")
    env = dict(image_env)
    ensure_default_region(env)
    env.update({
        "SESSION_ID": payload.run_id,
        "USECASE_ID": payload.usecase_id,
        "S3_BUCKET": payload.s3_bucket,
    })
    return env


def build_wizard_command() -> list[str]:
    return ["python", "wizard_worker.py"]


# ── the supervisor ──────────────────────────────────────────────────


class Supervisor:
    """Owns the single child of this VM. Thread-safe; one instance per process."""

    def __init__(
        self,
        *,
        image_env: Optional[Mapping[str, str]] = None,
        popen: Popen = subprocess.Popen,
        killpg: Killpg = os.killpg,
        terminate: Terminate = terminate_microvm,
        credentials_resolver: CredentialsResolver = resolve_credentials,
        cli_run: CliRun = subprocess.run,
        timing: Optional[SupervisorTiming] = None,
        cwd: str = DEFAULT_CWD,
    ) -> None:
        self._image_env = image_env
        self._popen = popen
        self._killpg = killpg
        self._terminate = terminate
        self._resolve_credentials = credentials_resolver
        self._cli_run = cli_run
        self._timing = timing or SupervisorTiming()
        self._cwd = cwd

        self._lock = threading.Lock()
        self._child: Any = None
        self._payload: Optional[RunPayload] = None
        self._microvm_id: Optional[str] = None
        self._exited = threading.Event()
        self._terminate_hook_called = False

    # -- hooks ------------------------------------------------------

    def health(self) -> tuple[int, dict]:
        """``/ready`` and ``/validate``: the CLI must be installed and importable."""
        cmd = list(CLI_HEALTH_COMMAND)
        try:
            result = self._cli_run(cmd, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as exc:
            logger.error("%s failed to start: %s", " ".join(cmd), exc)
            return 503, {"status": "not_ready", "error": str(exc)}
        if result.returncode != 0:
            logger.error("%s exited %s: %s", " ".join(cmd), result.returncode, result.stderr.strip())
            return 503, {"status": "not_ready", "error": f"{' '.join(cmd)} exited {result.returncode}"}
        return 200, {"status": "ready", "qa_studio": result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""}

    def run(self, raw_body: bytes) -> tuple[int, dict]:
        """``/run``: validate, build env, spawn, arm the watchdog, return."""
        microvm_id: Optional[str] = None
        try:
            microvm_id, hook_payload = parse_run_hook_body(raw_body)
            payload = RunPayload.from_hook_payload(hook_payload)
        except PayloadTooLargeError as exc:
            return self._reject(400, str(exc), microvm_id)
        except ValidationError as exc:
            return self._reject(400, f"invalid runHookPayload: {exc}", microvm_id)
        except ValueError as exc:
            return self._reject(400, str(exc), microvm_id)

        with self._lock:
            if self._child is not None:
                logger.error("/run called twice; already supervising %s", self._payload.run_id if self._payload else "?")
                return 409, {"error": "a child is already running"}

            image_env = dict(os.environ if self._image_env is None else self._image_env)
            # The supervisor's own boto3 clients (SSM, Secrets Manager,
            # TerminateMicrovm) read the process env, so set it there too.
            region = ensure_default_region(image_env)
            if region and not os.environ.get("AWS_DEFAULT_REGION"):
                os.environ["AWS_DEFAULT_REGION"] = region
            try:
                if payload.mode == "batch":
                    credentials = self._resolve_credentials(image_env)
                    env = build_batch_env(payload, image_env, credentials)
                    cmd = build_batch_command(payload, image_env)
                else:
                    env = build_wizard_env(payload, image_env)
                    cmd = build_wizard_command()
            except SupervisorConfigError as exc:
                return self._reject(500, str(exc), microvm_id)

            logger.info("Spawning %s child for %s: %s", payload.mode, payload.run_id, " ".join(cmd))
            logger.debug("Child env: %s", mask_env(env))
            try:
                child = self._popen(cmd, env=env, cwd=self._cwd, start_new_session=True)
            except OSError as exc:
                return self._reject(500, f"failed to spawn child: {exc}", microvm_id)

            self._child = child
            self._payload = payload
            self._microvm_id = microvm_id
            started_at = time.monotonic()

        threading.Thread(
            target=self._reap, args=(payload, child, started_at, microvm_id), name="supervisor-reaper", daemon=True,
        ).start()
        threading.Thread(target=self._watchdog, args=(payload, child), name="supervisor-watchdog", daemon=True).start()
        return 200, {"status": "started", "mode": payload.mode, "execution_id": payload.run_id}

    def terminate_hook(self) -> tuple[int, dict]:
        """``/terminate``: stop the child gracefully within the platform's window."""
        with self._lock:
            self._terminate_hook_called = True
            child = self._child
        if child is None or child.poll() is not None:
            return 200, {"status": "terminated", "child_exit_code": None if child is None else child.returncode}

        logger.info("/terminate: SIGTERM to child group %s", child.pid)
        self._signal_group(child, signal.SIGTERM)
        if not self._exited.wait(self._timing.terminate_wait_s):
            logger.warning("/terminate: child %s still alive after %ss; SIGKILL", child.pid, self._timing.terminate_wait_s)
            self._signal_group(child, signal.SIGKILL)
            self._exited.wait(self._timing.sigkill_grace_s)
        return 200, {"status": "terminated", "child_exit_code": child.returncode}

    # -- internals --------------------------------------------------

    def _reject(self, status: int, error: str, microvm_id: Optional[str]) -> tuple[int, dict]:
        logger.error("/run rejected (%s): %s", status, error)
        self._terminate(microvm_id)
        return status, {"error": error}

    def _signal_group(self, child: Any, sig: int) -> None:
        try:
            self._killpg(child.pid, sig)
        except ProcessLookupError:
            logger.info("Child group %s already gone before signal %s", child.pid, sig)

    def _watchdog(self, payload: RunPayload, child: Any) -> None:
        delay = soft_timeout_seconds(payload.max_duration_s, self._timing.soft_grace_s)
        logger.info("Watchdog armed: soft timeout in %.0fs (ceiling %ss)", delay, payload.max_duration_s)
        if self._exited.wait(delay):
            return
        logger.warning("Soft timeout for %s: SIGTERM to child group %s", payload.run_id, child.pid)
        self._signal_group(child, signal.SIGTERM)
        if not self._exited.wait(self._timing.sigkill_grace_s):
            logger.error("Child %s ignored SIGTERM for %ss; SIGKILL", child.pid, self._timing.sigkill_grace_s)
            self._signal_group(child, signal.SIGKILL)

    def _reap(self, payload: RunPayload, child: Any, started_at: float, microvm_id: Optional[str]) -> None:
        exit_code = child.wait()
        self._exited.set()
        duration_s = round(time.monotonic() - started_at, 3)
        # One JSON line per child exit. Exit codes are logged, not interpreted:
        # the runner uses 143 for `terminated` and 3 for `timeout`.
        logger.info(json.dumps({
            "event": "child_exit",
            "mode": payload.mode,
            "execution_id": payload.run_id,
            "exit_code": exit_code,
            "duration_s": duration_s,
            "microvm_id": microvm_id,
        }, sort_keys=True))
        with self._lock:
            skip = self._terminate_hook_called
        if skip:
            logger.info("Child exited during /terminate; the platform is already terminating this VM")
            return
        self._terminate(microvm_id)


# ── HTTP server ─────────────────────────────────────────────────────


class HookHandler(BaseHTTPRequestHandler):
    """Routes ``POST /aws/lambda-microvms/runtime/v1/<hook>`` to the supervisor."""

    supervisor: Supervisor  # set by make_server
    server_version = "qa-studio-supervisor"
    sys_version = ""

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: D401 — BaseHTTPRequestHandler hook
        logger.info("http %s", fmt % args)

    def do_GET(self) -> None:  # noqa: N802 — http.server naming
        self._reply(405, {"error": "hooks are POST only"})

    def do_POST(self) -> None:  # noqa: N802 — http.server naming
        if not self.path.startswith(HOOK_PREFIX):
            self._reply(404, {"error": "unknown path"})
            return
        hook = self.path[len(HOOK_PREFIX):].split("?", 1)[0].strip("/")
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""

        try:
            status, payload = self._dispatch(hook, body)
        except Exception:  # noqa: BLE001 — last line of defence: never drop the platform's connection
            logger.exception("Unhandled error in /%s hook", hook)
            status, payload = 500, {"error": f"internal error handling {hook}"}
        self._reply(status, payload)

    def _dispatch(self, hook: str, body: bytes) -> tuple[int, dict]:
        if hook in ("ready", "validate"):
            return self.supervisor.health()
        if hook == "run":
            return self.supervisor.run(body)
        if hook == "terminate":
            return self.supervisor.terminate_hook()
        if hook in ("suspend", "resume"):
            return 200, {"status": "ok", "hook": hook}
        return 404, {"error": f"unknown hook: {hook}"}

    def _reply(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def make_server(supervisor: Supervisor, *, host: str, port: int) -> ThreadingHTTPServer:
    handler = type("BoundHookHandler", (HookHandler,), {"supervisor": supervisor})
    return ThreadingHTTPServer((host, port), handler)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="QA Studio MicroVM supervisor")
    # The VM runs with the NO_INGRESS connector: the only client is the Lambda
    # platform's hook delivery, which is not loopback, and no port is published.
    # For a local `docker run`, publish as 127.0.0.1:8080:8080 (see README).
    parser.add_argument("--host", default=os.environ.get("SUPERVISOR_BIND_HOST", "0.0.0.0"))  # nosec B104
    parser.add_argument("--port", type=int, default=int(os.environ.get("SUPERVISOR_PORT", DEFAULT_PORT)))
    parser.add_argument("--cwd", default=os.environ.get("WORKER_APP_DIR", DEFAULT_CWD))
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=os.environ.get("SUPERVISOR_LOG_LEVEL", "INFO"),
        format="%(asctime)s supervisor %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    server = make_server(Supervisor(cwd=args.cwd), host=args.host, port=args.port)
    logger.info("Listening on %s:%s for MicroVM hooks", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Interrupted; shutting down")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
