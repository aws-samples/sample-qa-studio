# Spec: Trajectory-based Step Replay — Test Plan

**Companion to:** `trajectory-replay.md` and `trajectory-replay-spec.md`.
**Target coverage:** 70% unit (per steering `05_coding.md`). End-to-end for the full record → invalidate → re-record → replay cycle.

## Unit tests

### `web-app/worker/tests/test_trajectory_store.py` (new)

- `upload_trajectory` puts the right S3 key with the right bytes (mocked S3).
- `download_trajectory` returns local path when key exists; returns `None` when key missing (404 / NoSuchKey).
- `list_available_step_ids` parses step_ids from `list_objects_v2` response; returns empty set when prefix empty; handles pagination (or documents that pagination is unsupported if we don't implement it).
- `delete_all_trajectories` handles empty prefix (no-op), single object, multiple objects; returns accurate count.

### `web-app/worker/tests/test_navigation_step.py` (rewrite of deleted cache tests)

Replace the three deleted `test_navigation_step_cache_*.py` files with a single `test_navigation_step.py`:

- **Replay hit path:** `replay_mode=True` + `trajectory_path` set → calls `load_trajectory` + `replay_trajectory(strict=False)`, does NOT call `nova.act`.
- **Replay fallback:** `replay_mode=True`, `replay_trajectory` raises → falls through to `nova.act(step.instruction)`, returns live result.
- **Live path:** `replay_mode=False` → calls `nova.act` directly; on success calls `upload_trajectory` with `result.trajectory_file_path`.
- **Live path upload failure is non-fatal:** `upload_trajectory` raises → step still reports success, upload error logged.
- **`nova.act` failure:** returns `success=False`, does NOT upload a trajectory.

Mock the SDK's `load_trajectory` and `replay_trajectory` — no live SDK calls in unit tests.

### `web-app/lambdas/endpoints/test_trajectory_invalidator.py` (new)

- Event `step.created` → calls `delete_all_trajectories(usecase_id)`.
- Event `step.updated` → same.
- Event `step.deleted` → same.
- Event `usecase.cache_disabled` → same.
- Event `usecase.execution.completed` + `execution_status=failed` → same.
- Event `usecase.execution.completed` + `execution_status=success` → no-op.
- Missing `usecase_id` in detail → logged, no raise.
- `delete_objects` error → logged, no raise (fire-and-forget).

### Event emission tests in step mutation endpoints

For each of `create_step`, `update_step`, `delete_step`, `update_usecase`:

- Happy path emits the correct event with correct detail.
- EventBridge `put_events` failure → endpoint still returns 2xx (fire-and-forget); error logged.
- `update_usecase`: event emitted **only** on `enable_cache` true→false transition; not on false→true, not on no-change, not on other field updates.

## End-to-end test

**Target:** `testcases/app/create_usecase_with_cache.json` already exists. Either extend it or add a new testcase `trajectory_replay.json` with this user journey (per steering `05_coding.md`, new features need E2E tests):

1. Create a usecase with caching enabled.
2. Run it. Assert execution succeeds. Assert trajectories exist in S3 under `{usecase_id}/trajectories/`.
3. Run it again. Assert execution succeeds. Assert worker logs indicate replay mode was used (observability signal — see "Logging" below).
4. Edit a step. Assert trajectories were deleted (S3 prefix empty).
5. Run again. Assert live Nova Act path used. Assert trajectories repopulated.
6. Force a failure (introduce a bad step, or assert against impossible condition). Assert trajectories deleted on failed execution.

## Logging / observability contract

Tests should assert these log lines exist (or equivalent), since they're the only way to verify which code path ran in an E2E test:

- `Replay mode enabled for execution={exec_id}: {n} navigation steps covered`
- `Replay mode disabled for execution={exec_id}: missing trajectories for steps {ids}`
- `Replayed step {sort} in {duration_ms}ms`
- `Replay failed for step {sort}: {error}, falling back to live`
- `Uploaded trajectory for step {step_id} to s3://{bucket}/{key}`
- `Invalidator deleting {n} trajectory files for usecase {usecase_id} (trigger: {detail_type})`

## Coverage targets

Per `05_coding.md`: 70% unit. The deletion of ~5 cache test files is compensated by the new trajectory tests — target is that overall line coverage does not regress.

## Not tested (explicit)

- SDK behavior itself (`replayable=True`, `replay_trajectory`). Mocked in unit tests. The E2E test exercises real SDK behavior in a Fargate task; if the SDK breaks, the E2E will fail and the probe assumptions in `trajectory-replay.md` need revisiting.
- Validation during replay. We pass `strict=False` and do not verify validator output. If the SDK emits warnings from disabled-but-still-running validators, they're ignored.
- Race conditions between invalidation events and in-flight executions. Accepted: an execution that starts while invalidation is processing may either replay (old trajectories) or run live (trajectories gone). Both are correct behaviors.
