"""API access for TUI screens.

Thin UI-shaped facade over :class:`UseCaseAPI` and
:class:`TestSuiteAPI`. No endpoint is re-implemented here — list /
detail / sub-resource calls all delegate to the existing API modules.
The facade's job is:

1. Translate raw dict payloads into UI-friendly dataclasses
   (``UsecaseListItem``, ``SuiteListItem``) so screen code is
   decoupled from the backend's field-name variations.
2. Swallow optional sub-resource 404s (headers / secrets) so a missing
   sub-resource doesn't abort the whole detail load.

Screens call these helpers via ``asyncio.to_thread`` so the Textual
event loop stays responsive during HTTP requests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from qa_studio_cli.api.client import ApiClient, build_api_client as _build_api_client
from qa_studio_cli.api.test_suites import TestSuiteAPI
from qa_studio_cli.api.usecases import UseCaseAPI
from qa_studio_cli.models.config import CLIConfig


def build_api_client(config: Optional[CLIConfig] = None) -> ApiClient:
    """Thin alias for :func:`qa_studio_cli.api.client.build_api_client`.

    Kept as a named import so screens / tests that need to stub the
    builder can patch ``qa_studio_cli.tui.api.build_api_client``
    without reaching into the ``api.client`` module.
    """
    return _build_api_client(config=config)


@dataclass(frozen=True)
class UsecaseListItem:
    """Shape of a row on the Usecases list screen.

    Extracted from the raw API payload so the screen code is
    independent of which field names the backend happens to use
    (snake vs camel case, optional fields, etc.)."""

    usecase_id: str
    name: str
    platform: str
    region: str

    @classmethod
    def from_api(cls, raw: Dict[str, Any]) -> "UsecaseListItem":
        return cls(
            usecase_id=str(raw.get("id") or raw.get("usecase_id") or ""),
            name=str(raw.get("name") or "—"),
            platform=str(raw.get("test_platform") or raw.get("platform") or "web"),
            region=str(raw.get("executing_region") or raw.get("region") or "—"),
        )


@dataclass(frozen=True)
class SuiteListItem:
    """Shape of a row on the Test suites list screen."""

    suite_id: str
    name: str
    total_usecases: int
    description: str

    @classmethod
    def from_api(cls, raw: Dict[str, Any]) -> "SuiteListItem":
        return cls(
            suite_id=str(raw.get("id") or raw.get("suite_id") or ""),
            name=str(raw.get("name") or "—"),
            total_usecases=int(raw.get("total_usecases") or 0),
            description=str(raw.get("description") or ""),
        )


@dataclass(frozen=True)
class ExecutionListItem:
    """Shape of a row on the Executions tab of the usecase detail.

    Fields are pulled from the raw API payload defensively so that
    records missing a duration or creator still render (a blank cell
    is fine; a crash is not)."""

    execution_id: str
    status: str
    created_at: str
    duration_seconds: float
    trigger_type: str
    triggered_by: str

    @classmethod
    def from_api(cls, raw: Dict[str, Any]) -> "ExecutionListItem":
        def _num(value: Any) -> float:
            try:
                return float(value) if value is not None else 0.0
            except (TypeError, ValueError):
                return 0.0

        # The server returns raw DynamoDB items from the list-executions
        # endpoint — the execution id only lives in the sort key
        # (``EXECUTION#<id>``), not as a top-level field. We fall back
        # to parsing the sk when neither ``execution_id`` nor ``id``
        # is present so the row key maps back to a usable id on
        # selection.
        execution_id = str(
            raw.get("execution_id") or raw.get("id") or ""
        )
        if not execution_id:
            sk = str(raw.get("sk") or "")
            prefix = "EXECUTION#"
            if sk.startswith(prefix):
                execution_id = sk[len(prefix):]

        return cls(
            execution_id=execution_id,
            status=str(raw.get("status") or "—"),
            created_at=str(raw.get("created_at") or "—"),
            duration_seconds=_num(raw.get("duration_seconds") or raw.get("duration")),
            trigger_type=str(raw.get("trigger_type") or "—"),
            triggered_by=str(raw.get("triggered_by") or "—"),
        )


class TuiApi:
    """Synchronous UI-shaped facade over the read-side API modules.

    Separated from the Textual screens so it can be unit-tested with a
    mocked ``ApiClient`` and so the screens' threading boundary is
    obvious: every method here is sync; screens wrap the call in
    ``asyncio.to_thread`` (or Textual's ``@work(thread=True)``).
    """

    def __init__(self, client: ApiClient):
        self._client = client
        self._usecase_api = UseCaseAPI(client)
        self._suite_api = TestSuiteAPI(client)

    # ------------------------------------------------------------------
    # Use cases
    # ------------------------------------------------------------------

    def list_usecases(self) -> List[UsecaseListItem]:
        raw_items = self._usecase_api.list_usecases()
        return [UsecaseListItem.from_api(raw) for raw in raw_items]

    def get_usecase(self, usecase_id: str) -> Dict[str, Any]:
        return self._usecase_api.get_usecase(usecase_id)

    def get_steps(self, usecase_id: str) -> List[Dict[str, Any]]:
        return self._usecase_api.get_steps(usecase_id)

    def get_variables(self, usecase_id: str) -> Dict[str, str]:
        return self._usecase_api.get_variables(usecase_id)

    def get_headers(self, usecase_id: str) -> Dict[str, str]:
        try:
            return self._usecase_api.get_headers(usecase_id)
        except Exception:
            # Headers is a sub-resource that can 404 on older usecases.
            # Detail screen treats "no headers" as an empty dict; we
            # do not want the whole detail load to fail because of a
            # missing sub-resource.
            return {}

    def get_secrets(self, usecase_id: str) -> List[Dict[str, Any]]:
        try:
            return self._usecase_api.get_secrets(usecase_id)
        except Exception:
            return []

    def list_executions(
        self, usecase_id: str, limit: int = 20
    ) -> List[ExecutionListItem]:
        """Recent executions for a use case (newest first).

        Tolerates transport / API failures by returning an empty list
        — the detail screen treats "no executions" as a legitimate
        empty state, and a 404 on older usecases shouldn't prevent the
        rest of the detail from loading.
        """
        try:
            raw_items = self._usecase_api.list_executions(usecase_id, limit=limit)
        except Exception:
            return []
        return [ExecutionListItem.from_api(raw) for raw in raw_items]

    def get_execution_metadata(
        self, usecase_id: str, execution_id: str
    ) -> Dict[str, Any]:
        """Fetch just the execution's metadata record.

        Split out from :meth:`get_execution_detail` so callers that
        want progressive rendering (the TUI) can request the main
        record independently from steps / variables / headers and
        paint it as soon as it arrives.

        Errors bubble up — the TUI's progressive loader turns each
        section failure into an inline message rather than aborting
        the whole screen.
        """
        return self._client.get(
            f"/usecase/{usecase_id}/executions/{execution_id}"
        )

    def get_execution_steps(
        self, usecase_id: str, execution_id: str
    ) -> List[Dict[str, Any]]:
        """Fetch the step results for a single execution.

        Returns the unwrapped list (``[]`` when the response carries
        no ``steps`` key). Errors bubble — same rationale as
        :meth:`get_execution_metadata`.
        """
        response = self._client.get(
            f"/usecase/{usecase_id}/executions/{execution_id}/steps"
        )
        return response.get("steps", []) or []

    def get_execution_detail(
        self, usecase_id: str, execution_id: str
    ) -> Dict[str, Any]:
        """Compose the execution detail payload in a single sync call.

        Mirrors :meth:`ExecutionAPI.get_execution` but is
        synchronous so it can be called from a Textual ``@work(thread=True)``
        worker without wrapping in ``asyncio.run``. The returned dict
        carries the usual execution metadata plus ``steps`` /
        ``variables`` / ``headers`` sub-payloads. Sub-resource failures
        are swallowed (empty fallback) because older executions may
        not have every endpoint available.

        Note: the TUI's :class:`ExecutionDetailScreen` no longer calls
        this composite. It now drives the two rendered sections
        (``get_execution_metadata`` and ``get_execution_steps``) in
        parallel via :mod:`asyncio`. The composite is kept for
        callers that want a single blocking call (and for the direct
        tests in ``test_tui_execution_detail``).
        """
        execution = self._client.get(
            f"/usecase/{usecase_id}/executions/{execution_id}"
        )

        try:
            steps_response = self._client.get(
                f"/usecase/{usecase_id}/executions/{execution_id}/steps"
            )
            execution["steps"] = steps_response.get("steps", []) or []
        except Exception:
            execution["steps"] = []

        try:
            vars_response = self._client.get(
                f"/usecase/{usecase_id}/executions/{execution_id}/variables"
            )
            exec_vars = vars_response.get("execution_variables", {})
            if isinstance(exec_vars, dict) and exec_vars:
                execution["variables"] = exec_vars
            else:
                raw_vars = vars_response.get("variables", [])
                merged: Dict[str, str] = {}
                if isinstance(raw_vars, list):
                    for entry in raw_vars:
                        if isinstance(entry, dict) and "key" in entry and "value" in entry:
                            merged[entry["key"]] = entry["value"]
                elif isinstance(raw_vars, dict):
                    merged = raw_vars
                execution["variables"] = merged
        except Exception:
            execution["variables"] = {}

        try:
            headers_response = self._client.get(
                f"/usecase/{usecase_id}/executions/{execution_id}/headers"
            )
            execution["headers"] = headers_response.get("headers", {}) or {}
        except Exception:
            execution["headers"] = {}

        return execution

    # ------------------------------------------------------------------
    # Test suites
    # ------------------------------------------------------------------

    def list_suites(self) -> List[SuiteListItem]:
        raw_items = self._suite_api.list_suites()
        return [SuiteListItem.from_api(raw) for raw in raw_items]

    def get_suite(self, suite_id: str) -> Dict[str, Any]:
        return self._suite_api.get_suite(suite_id)

    def list_suite_usecases(self, suite_id: str) -> List[Dict[str, Any]]:
        return self._suite_api.list_usecases(suite_id)

    def list_suite_executions(
        self, suite_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Recent executions for a test suite (newest first).

        Tolerates transport / API failures by returning an empty
        list — the suite-detail Executions tab treats "no executions"
        as a legitimate empty state, and a 404 on older suites
        shouldn't break the rest of the detail load.
        """
        try:
            return self._suite_api.list_executions(suite_id, limit=limit)
        except Exception:
            return []
