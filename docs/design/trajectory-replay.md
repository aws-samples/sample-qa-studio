# Design: Trajectory-based Step Replay

**Status:** Draft — awaiting SDK probe verification before implementation.
**Supersedes:** the existing bbox-based step cache (`cache_parser.py`, `cache_executor.py`, `build_cache.py` lambda).

## Problem

QA Studio re-runs the same test cases repeatedly (regression, CI, scheduled). On each run, Nova Act invokes its vision model per navigation step, costing 2–5s of LLM latency and dollars per step. We already have a cache system that regex-parses Nova Act's internal `rawProgramBody` format from S3 artifacts and replays actions via Playwright. It works, but it depends on an **undocumented internal Nova Act string format** that can break silently on any SDK upgrade.

Amazon Nova Act ships (per the referenced AWS Builder blog, April 2026) a `replayable=True` flag that makes the SDK emit a structured **trajectory JSON** per `act()` call and replay it via the SDK's own program runner — no regex, no format-guessing. This is a more reliable source of record for the same replay problem we already solved.

## Goals

- Replace the current bbox-based cache with trajectory-based replay.
- Keep the existing `enable_cache` user toggle and UI surface (no user-visible UX change for the toggle itself).
- Replay skips the LLM (preserves the speed win).
- Do **not** run URL / DOM / screenshot validators during replay (explicitly not in scope).
- Net code reduction: delete more than we add.

## Non-goals

- UI regression validation (URL / DOM / screenshot diff from the blog). Not shipping — user opted out.
- Mobile (Device Farm) replay. Out of scope; trajectory replay assumes Playwright.
- Partial caching. All-or-nothing per usecase execution.
- HTML validation report from the blog. Not shipping.
- Flakiness detection via repeated replays. Follow-on.

## User journey

**Author a usecase with caching enabled.**
1. User creates a usecase, enables "Step caching" toggle in the edit form (unchanged UI).
2. User runs the usecase. Nova Act executes live. On success, the worker uploads one trajectory JSON per navigation step to S3.
3. User re-runs the usecase. The worker detects all navigation steps have trajectory files. It replays via the SDK's program runner. No LLM calls. Same result, faster.

**A step is edited.**
1. User edits the instruction of step 3. On save, API emits `step.updated`. Invalidator lambda deletes `s3://{bucket}/{usecase_id}/trajectories/` prefix.
2. Next run: no trajectories → full live Nova Act run → on success, new trajectories uploaded.

**An execution fails.**
1. Any execution failure (navigation step, validation step, anything) → worker emits `usecase.execution.completed` with `execution_status=failed` (already emitted today).
2. Invalidator lambda subscribes to failed executions, deletes the trajectory prefix.
3. Next run: re-records from scratch.

**Caching toggled off.**
1. User disables the toggle. API emits `usecase.cache_disabled`. Invalidator deletes prefix.

## High-level design

```
┌───────────────────────────────────────────────────────────────────┐
│                        CAPTURE (on success)                        │
│                                                                    │
│  worker/navigation_step.py                                        │
│     │                                                              │
│     │  nova.act(instruction)  ──►  SDK writes                      │
│     │                              logs_dir/.../act_*_trajectory.json │
│     │  result.trajectory_file_path                                 │
│     │                                                              │
│     └──►  upload bytes to                                          │
│           s3://{bucket}/{usecase_id}/trajectories/{step_id}.json  │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│                    REPLAY (eligibility + execute)                  │
│                                                                    │
│  worker/worker.py (start of execution)                            │
│     │                                                              │
│     │  list_objects_v2({usecase_id}/trajectories/)                │
│     │  Build set of step_ids with trajectories.                    │
│     │  If set covers ALL navigation steps → replay_mode = True    │
│     │  Else → replay_mode = False                                  │
│     ▼                                                              │
│  worker/navigation_step.py (per step)                             │
│     │                                                              │
│     │  if replay_mode and step_id in trajectory_set:              │
│     │      get_object  →  load_trajectory(local_path)             │
│     │      nova.replay_trajectory(traj, strict=False)             │
│     │      (validators disabled — see Assumptions below)          │
│     │  else:                                                       │
│     │      nova.act(instruction)                                   │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│                          INVALIDATION                              │
│                                                                    │
│  Trigger                 │ Emitted by              │ Event         │
│  ─────────────────────── │ ───────────────────────│ ───────────── │
│  step created            │ create_step lambda     │ step.created  │
│  step updated            │ update_step lambda     │ step.updated  │
│  step deleted            │ delete_step lambda     │ step.deleted  │
│  enable_cache = false    │ update_usecase lambda  │ usecase.      │
│                          │                        │ cache_disabled│
│  execution failed        │ worker (existing)      │ usecase.      │
│                          │                        │ execution.    │
│                          │                        │ completed     │
│                          │                        │ (status=fail) │
│                                                                    │
│       ALL ──►  trajectory_invalidator lambda                      │
│                   │                                                │
│                   │  list_objects_v2({usecase_id}/trajectories/)  │
│                   │  delete_objects(...)                           │
│                   ▼                                                │
│                clean slate                                         │
└───────────────────────────────────────────────────────────────────┘
```

## Data model

### S3 layout

| Key | Purpose | Written by | Deleted by |
|---|---|---|---|
| `{usecase_id}/trajectories/{step_id}.json` | Per-step trajectory JSON from `result.trajectory_file_path` | `navigation_step.py` post-success | `trajectory_invalidator` lambda |

No bundle file. No per-execution subdirectory.

### DynamoDB

No new columns strictly required. Keep `STEP.cached_steps` and `STEP.cache_last_updated` columns defined in `models.py` but stop reading/writing them. Cleanup of dead columns is a follow-on (DDB is schemaless — leaving them is harmless).

Existing `USECASE.enable_cache` (bool) is reused as-is.

Existing `EXECUTION.enable_cache` (bool, propagated from usecase at execution start) is reused as-is.

Existing `EXECUTION_STEP.act_id` (captured today) remains.

### Event schemas

New events from the mutation endpoints:

```json
{
  "Source": "nova-act-qa-studio.usecase",
  "DetailType": "step.created" | "step.updated" | "step.deleted",
  "Detail": {
    "usecase_id": "uc_abc",
    "step_id": "st_xyz",
    "timestamp": "2026-04-22T10:00:00Z"
  }
}
```

```json
{
  "Source": "nova-act-qa-studio.usecase",
  "DetailType": "usecase.cache_disabled",
  "Detail": {
    "usecase_id": "uc_abc",
    "timestamp": "2026-04-22T10:00:00Z"
  }
}
```

Reused events (already emitted):

```json
{
  "Source": "nova-act-qa-studio.execution" (or "qa-studio.worker"),
  "DetailType": "usecase.execution.completed",
  "Detail": {
    "usecase_id": "uc_abc",
    "execution_id": "ex_xyz",
    "execution_status": "failed" | "success",
    "timestamp": "..."
  }
}
```

The invalidator lambda filters on `execution_status == "failed"` for this event type; ignores other detail-types.

## Trajectory JSON shape (from blog, to be verified)

Per the blog, one file per `act()` call:

```json
{
  "sdk_version": "3.2.216.0",
  "prompt": "Go to the Destinations page",
  "steps": [
    {
      "active_url": "https://...",
      "image": "data:image/jpeg;base64,...",
      "simplified_dom": "<body>...</body>",
      "program": {
        "calls": [
          {"name": "think",         "kwargs": {"value": "..."}},
          {"name": "agentClick",    "kwargs": {"box": "<box>32,503,55,595</box>"}},
          {"name": "waitForPageToSettle", "kwargs": {}},
          {"name": "takeObservation",     "kwargs": {}}
        ]
      }
    }
  ],
  "metadata": {
    "session_id": "...",
    "act_id": "...",
    "num_steps_executed": 2,
    "prompt": "Go to the Destinations page"
  }
}
```

## Assumptions to verify before implementation (SDK probe)

The following behaviors are assumed from the blog but not yet confirmed against our pinned `nova-act` Python package. The probe must answer each before this design is locked.

| # | Assumption | Consequence if false |
|---|---|---|
| A1 | `NovaAct(replayable=True)` exists in the target SDK version | Doc invalid; need Plan B (fork, subclass, or stay on current cache) |
| A2 | `ActResult.trajectory_file_path` exists and returns a local path | Capture step cannot read the file; need alternative capture |
| A3 | A public `load_trajectory()` and `replay_trajectory(nova, traj, strict=False)` (or equivalent `nova.replay(...)`) exist | Need to build our own program runner against `program.calls` — undoing the main reason for this refactor |
| A4 | `strict=False` suppresses the validators entirely, or an option exists to disable them | Cost: screenshot + DOM capture runs every replay for nothing. Not fatal. Accept and ignore warning output if no disable-entirely option |
| A5 | Replay matches trajectories positionally within a single `NovaAct` session (not per-act-call isolation) | Per-step replay model may not work; may need to replay all trajectories in one `NovaAct` block |
| A6 | Extraction-style `act()` calls (our `retrieve_value_step`, schema-based validation) produce usable trajectories, or are out of scope for replay | If they don't, replay remains navigation-only (matches current cache scope). Not fatal. |
| A7 | SDK version bump does not break other worker code paths | Run existing worker tests post-bump |

**Until probe results are in, do not start implementation. Update this doc with verified results, then proceed.**

## What gets removed

- `web-app/worker/cache_parser.py`
- `web-app/worker/cache_executor.py`
- `web-app/worker/demo_cache_parser.py`
- `web-app/lambdas/endpoints/build_cache.py` (and its EventBridge rule in CDK `worker-stack.ts` or `lambda-stack.ts`)
- `web-app/lambdas/endpoints/worker/cache_parser.py` (duplicate)
- Cache-related tests:
  - `web-app/worker/tests/test_cache_parser.py`
  - `web-app/worker/tests/test_cache_executor.py`
  - `web-app/worker/tests/test_navigation_step_cache_hit.py`
  - `web-app/worker/tests/test_navigation_step_cache_miss.py`
  - `web-app/worker/tests/test_navigation_step_cache_failure.py`
  - `web-app/lambdas/endpoints/test_build_cache.py`
  - `web-app/lambdas/endpoints/test_list_steps_cache.py`
  - `web-app/lambdas/endpoints/test_execute_usecase_cache.py` (rewrite for trajectory, don't delete)
- `CACHE_ACTION_DELAY_MS` env var and documentation

What stays:
- `USECASE.enable_cache` field, edit form toggle, API propagation
- `EXECUTION.enable_cache` propagation in `execute_usecase.py`
- `EXECUTION_STEP.act_id` capture
- `usecase.execution.completed` event emission

## What gets added

- Dependency bump: `nova-act` to a version supporting `replayable=True` (exact version from probe)
- `web-app/worker/trajectory_store.py` — small module: `upload_trajectory(s3, bucket, usecase_id, step_id, local_path)`, `download_trajectory(s3, bucket, usecase_id, step_id, dest_dir) -> local_path | None`, `list_available_trajectories(s3, bucket, usecase_id) -> set[str]`
- Changes to `web-app/worker/navigation_step.py` — replace `execute_cached_steps()` call with `nova.replay_trajectory(...)` when eligible; upload trajectory after successful `nova.act()`
- Changes to `web-app/worker/worker.py` — at execution start (after loading steps), if `enable_cache=True`, list trajectories and compute `replay_mode` (all navigation steps covered or not)
- New lambda: `web-app/lambdas/endpoints/trajectory_invalidator.py` (or add to existing lambdas folder structure) — subscribed to step mutation events and failed execution events
- CDK: new EventBridge rules for step mutation events → invalidator; existing failed-execution rule → invalidator (or adapt existing `build_cache` rule and rename)
- Step mutation endpoints (`create_step.py`, `update_step.py`, `delete_step.py`) — emit the new events (they currently do not)
- `update_usecase.py` — when `enable_cache` transitions from `true` to `false`, emit `usecase.cache_disabled`
- Frontend `StepsTable.tsx` — the "Cached" badge per step becomes a usecase-level badge (single source of truth, from S3 listing exposed via a new `GET /usecases/{id}/cache-status` endpoint, or from a derived field on the usecase response)

## Open questions / risks

1. **Probe results may kill this design.** See A1–A5. If the SDK doesn't expose the expected API, we either stay with the current cache (my recommendation if upstream is blocker) or subclass `NovaAct` to capture trajectory data ourselves (more code, more maintenance).
2. **Silent regression re-baselining** (previously discussed). Accepted trade per user decision: on execution failure, trajectory is deleted. No badge surfaces this state in v1.
3. **`logs_directory` layout.** The SDK writes trajectory files under `logs_directory/{session_id}/`. The worker currently uses a per-execution logs directory. Need to confirm that `result.trajectory_file_path` returns the path reliably within an ECS task (file IO permissions, lifetime).
4. **Replay across sessions.** The blog's `replay.py` opens a fresh `NovaAct()` and calls `replay_trajectory(nova, traj)`. Our worker opens **one** `NovaAct` block per execution and runs N navigation steps inside it. Need to confirm that calling `replay_trajectory` N times within one `NovaAct` context manager works correctly, or whether each replay needs its own NovaAct block (would be a much bigger refactor).
5. **Extraction steps (`retrieve_value_step`) don't emit trajectories suitable for replay** (A6 above). If that's the case, it's the same as today (extraction steps were never cached). Surfacing in doc so nobody is surprised.

## Rollout

1. **Phase 0:** SDK probe. Update this doc with results.
2. **Phase 1:** SDK version bump, run existing tests, ensure no regression.
3. **Phase 2:** Add trajectory capture in `navigation_step.py`. No replay yet. Verify trajectories land in S3 at the right key, format as expected. Existing bbox cache still active.
4. **Phase 3:** Add replay path + `replay_mode` gating in `worker.py`. Run both systems in parallel (bbox cache for users without trajectories yet, trajectory replay for users who have them). Observability: log which path was taken.
5. **Phase 4:** Invalidation lambda + event emission from step mutation endpoints.
6. **Phase 5:** Remove bbox cache code paths, tests, lambda, EventBridge rule. Remove `CACHE_ACTION_DELAY_MS`. Update docs (`user-guide.md`, `worker/README.md`, `configuration.md`).
7. **Phase 6:** Frontend — swap per-step badge for usecase-level badge (if kept).

## Testing

See `trajectory-replay-spec.md` for the detailed test matrix. Minimum bar:
- Capture writes the right S3 key with the right content on success.
- Capture does not write on Nova Act failure.
- Replay takes the replay path when all navigation steps have trajectories; takes the live path otherwise.
- Invalidator lambda deletes the whole prefix on each of the four trigger events.
- Execute-end-to-end test: record → invalidate → re-record → replay — validates the full cycle in one integration test.
