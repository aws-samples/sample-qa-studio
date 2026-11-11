"""``run_payload.py`` is a vendored, byte-identical copy of ``worker/supervisor_models.py``.

The launcher Lambda (``execute_usecase`` → ``microvm_launch``) serialises a
``RunPayload`` into ``RunMicrovm(runHookPayload=...)`` and the supervisor
inside the MicroVM parses it back.  ``Code.fromAsset('lambdas/endpoints')``
only packages this directory, so the model is duplicated rather than imported
across the tree; this test pins the two files to the same bytes so the wire
contract cannot drift.  To change the model: edit ``supervisor_models.py``,
then ``cp web-app/worker/supervisor_models.py web-app/lambdas/endpoints/run_payload.py``.
"""
import os

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_LAMBDA_COPY = os.path.join(_HERE, "run_payload.py")
_WORKER_SOURCE = os.path.abspath(os.path.join(_HERE, "..", "..", "worker", "supervisor_models.py"))


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


@pytest.mark.skipif(
    not os.path.exists(_WORKER_SOURCE),
    reason=f"worker checkout not present at {_WORKER_SOURCE} (lambda-only checkout)",
)
def test_run_payload_is_byte_identical_to_supervisor_models():
    assert _read_bytes(_LAMBDA_COPY) == _read_bytes(_WORKER_SOURCE), (
        "run_payload.py drifted from worker/supervisor_models.py; "
        "re-copy it: cp web-app/worker/supervisor_models.py web-app/lambdas/endpoints/run_payload.py"
    )


def test_run_payload_exports_the_launcher_contract():
    import run_payload

    for name in ("RunPayload", "MobileConfig", "PayloadTooLargeError", "RUN_HOOK_PAYLOAD_MAX_BYTES"):
        assert hasattr(run_payload, name), name
    payload = run_payload.RunPayload(
        mode="batch", usecase_id="uc", execution_id="ex", execution_token="s3cr3t-value",
        region="eu-central-1", s3_bucket="b-eu-central-1", max_duration_s=60,
    )
    raw = payload.to_hook_payload()
    assert "s3cr3t-value" in raw  # the token travels in the hook payload ...
    assert "s3cr3t-value" not in repr(payload)  # ... but never in repr/logs
    assert run_payload.RunPayload.from_hook_payload(raw) == payload
