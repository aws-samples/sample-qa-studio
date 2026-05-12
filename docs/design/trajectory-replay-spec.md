# Spec: Trajectory-based Step Replay — File-level Changes

**Companion to:** `trajectory-replay.md` (design doc).
**Status:** Draft — do not implement before SDK probe results land in the design doc.
**Test plan:** see `trajectory-replay-tests.md`.

## New files

### `web-app/worker/trajectory_store.py`

Small S3 helper. No business logic.

```python
def upload_trajectory(s3, bucket, usecase_id, step_id, local_path) -> None
def download_trajectory(s3, bucket, usecase_id, step_id, dest_dir) -> str | None
def list_available_step_ids(s3, bucket, usecase_id) -> set[str]
def delete_all_trajectories(s3, bucket, usecase_id) -> int  # returns count deleted
```

Key format: `{usecase_id}/trajectories/{step_id}.json`.
`list_available_step_ids` does one `list_objects_v2` and parses `step_id` from each key.

### `web-app/lambdas/endpoints/trajectory_invalidator.py`

EventBridge-triggered lambda. Handles four detail-types:
- `step.created`, `step.updated`, `step.deleted`: extract `usecase_id` from detail, call `delete_all_trajectories`.
- `usecase.cache_disabled`: same.
- `usecase.execution.completed` with `execution_status=failed`: same.

Fire-and-forget error handling (logs, never raises). Mirrors `build_cache.py`.

## Modified files

### `web-app/worker/navigation_step.py`

Replace the bbox-cache path with trajectory replay. Keep the fallback-to-`nova.act` behavior on replay exception.

Signature change: add `replay_mode: bool` and `trajectory_path: str | None` params (passed in from `worker.py`). Remove `enable_cache` logic (moved up to `worker.py`).

```python
def execute_navigation_step(nova, step, replay_mode=False, trajectory_path=None):
    if replay_mode and trajectory_path:
        try:
            traj = load_trajectory(trajectory_path)
            replay_trajectory(nova, traj, strict=False)
            return _cached_result(), True, ""
        except Exception as e:
            logger.warning(f"Replay failed for step {step.sort}: {e}, falling back")

    # Live execution (unchanged from today minus the cache branch)
    try:
        result = nova.act(step.instruction)
        _upload_trajectory_if_possible(result, step)  # best-effort, guarded by enable_cache
        return result, True, ""
    except Exception as e:
        # unchanged error handling
```

### `web-app/worker/worker.py`

At execution start, after loading steps and the NovaAct context is entered but before per-step dispatch:

```python
replay_mode = False
available_trajectories = {}  # step_id -> local_path
if execution.enable_cache:
    available = trajectory_store.list_available_step_ids(s3, bucket, usecase_id)
    nav_step_ids = {s.step_id for s in steps if s.step_type in (None, "navigation")}
    if nav_step_ids and nav_step_ids.issubset(available):
        replay_mode = True
        for sid in nav_step_ids:
            local = trajectory_store.download_trajectory(s3, bucket, usecase_id, sid, tmpdir)
            available_trajectories[sid] = local
```

Pass `replay_mode` and the per-step `trajectory_path` into `execute_navigation_step` in the step dispatch loop.

### `web-app/lambdas/endpoints/create_step.py`, `update_step.py`, `delete_step.py`

After successful DDB write, emit the corresponding event:

```python
eventbridge.put_events(Entries=[{
    "Source": "nova-act-qa-studio.usecase",
    "DetailType": "step.created",  # or .updated / .deleted
    "Detail": json.dumps({
        "usecase_id": usecase_id,
        "step_id": step_id,
        "timestamp": get_current_timestamp()
    }),
    "EventBusName": "default"
}])
```

Fire-and-forget (log failures, don't fail the API call). Extract to a helper `emit_step_event(detail_type, usecase_id, step_id)` in `utils.py` to avoid duplication.

### `web-app/lambdas/endpoints/update_usecase.py`

Detect `enable_cache` true→false transition (requires reading the existing record before update, or using a conditional expression). On transition, emit:

```python
eventbridge.put_events(Entries=[{
    "Source": "nova-act-qa-studio.usecase",
    "DetailType": "usecase.cache_disabled",
    "Detail": json.dumps({"usecase_id": usecase_id, "timestamp": ...}),
    "EventBusName": "default"
}])
```

### `web-app/worker/models.py`

No changes required. `ExecutionStep.cached_steps` / `cache_last_updated` remain defined but go unused. Remove in a follow-on cleanup once all in-flight trajectories are replaced.

### `web-app/lambdas/endpoints/execute_usecase.py`

Remove the `cached_steps` / `cache_last_updated` copy in the STEP → EXECUTION_STEP loop (~line 340). Keep `enable_cache` propagation to the EXECUTION record.

Remove the `CACHE_ACTION_DELAY_MS` env var from container overrides.

### `web-app/lib/lambda-stack.ts` (or wherever EventBridge rules are defined)

- Remove the `build_cache` lambda definition and its EventBridge rule.
- Add `trajectory_invalidator` lambda.
- Add EventBridge rules routing these detail-types to the invalidator:
  - `step.created`, `step.updated`, `step.deleted`, `usecase.cache_disabled` (source: `nova-act-qa-studio.usecase`)
  - `usecase.execution.completed` (source: existing worker/execution source, filtered on `execution_status=failed` via event pattern)

IAM: invalidator needs `s3:ListBucket`, `s3:DeleteObject` on the artifacts bucket.

### `web-app/frontend/src/components/StepsTable.tsx`

Remove per-step `cached_steps` / `cache_last_updated` badge logic. Replace with a usecase-level badge rendered by the parent usecase detail page (out of scope for this file, lives wherever the usecase header is rendered).

Data source for the new badge: add `trajectory_recorded` boolean + `trajectory_recorded_at` timestamp to the usecase GET response, computed server-side by listing S3 keys (cached or on-demand). Exact endpoint choice deferred to implementation time.

## Files to delete

- `web-app/worker/cache_parser.py`
- `web-app/worker/cache_executor.py`
- `web-app/worker/demo_cache_parser.py`
- `web-app/lambdas/endpoints/build_cache.py`
- `web-app/lambdas/endpoints/worker/cache_parser.py` (duplicate)
- `web-app/worker/tests/test_cache_parser.py`
- `web-app/worker/tests/test_cache_executor.py`
- `web-app/worker/tests/test_navigation_step_cache_hit.py`
- `web-app/worker/tests/test_navigation_step_cache_miss.py`
- `web-app/worker/tests/test_navigation_step_cache_failure.py`
- `web-app/lambdas/endpoints/test_build_cache.py`
- `web-app/lambdas/endpoints/test_list_steps_cache.py`

## Dependency changes

`web-app/worker/requirements.txt`: bump `nova-act` to the version confirmed by the probe to expose `replayable=True`, `trajectory_file_path`, `load_trajectory`, `replay_trajectory`.

## Documentation updates

- `docs/user-guide.md`: update the caching section if it describes bbox replay. Keep the user-facing description at the level of "caching speeds up re-runs."
- `docs/architecture.md`: replace bbox-cache diagram/description with trajectory flow.
- `web-app/worker/README.md`: replace the entire "Cache Execution" section (currently ~70 lines describing bbox replay) with a shorter trajectory section. Remove the cached action-types table, fallback-scenario table, and `CACHE_ACTION_DELAY_MS` reference.
- `docs/configuration.md`: remove `CACHE_ACTION_DELAY_MS` if listed.
