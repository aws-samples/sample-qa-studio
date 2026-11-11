# Troubleshooting Guide

This guide helps you diagnose and resolve common issues when using QA Studio.

## Web Application Issues

### Cannot Access Web Application

**Symptoms**:
- CloudFront URL returns 404 or Access Denied
- Page loads but shows blank screen

**Solutions**:

1. **Verify deployment completed successfully**:
   ```bash
   cd web-app
   npm run deploy
   ```

2. **Check CloudFront distribution status**:
   - Log into AWS Console
   - Navigate to CloudFront
   - Verify distribution is "Deployed" (not "In Progress")

3. **Clear browser cache**:
   - Hard refresh: Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (Mac)
   - Or clear browser cache completely

4. **Check S3 bucket**:
   - Verify frontend files were uploaded to S3
   - Check bucket policy allows CloudFront access

### Authentication Fails

**Symptoms**:
- Redirected to Cognito but login fails
- "User does not exist" error
- Infinite redirect loop

**Solutions**:

1. **Check Cognito user exists**:
   - Log into AWS Console → Cognito
   - Verify user exists in user pool
   - Check user status is "CONFIRMED"

2. **Reset password**:
   - Use "Forgot password" flow
   - Or reset via AWS Console

3. **Verify Cognito configuration**:
   - Check callback URLs match CloudFront URL
   - Verify OAuth scopes are configured
   - Check app client settings

4. **Clear browser cookies**:
   - Cognito stores session in cookies
   - Clear cookies for your domain

### Test Execution Fails

**Symptoms**:
- Test starts but never completes
- Test fails immediately
- No artifacts generated

**Solutions**:

1. **Check the worker logs**:
   - Open the execution in the web UI and follow the **CloudWatch Logs** link (`cloudwatch_logs_url`): the stream named after the execution id in `/qa-studio/<baseName>/microvm`.
   - MicroVM-specific symptoms: see [MicroVM worker](#microvm-worker) below.

2. **Check the launch result**:
   - `POST /usecase/{id}/execute` returns `500 {"error": "Failed to start MicroVM: …"}` and marks the execution `failed` with the same text when the VM could not be started (after 5 `RunMicrovm` attempts on `ThrottlingException`).

3. **Check Nova Act configuration**:
   - Verify Bedrock model access
   - Check IAM permissions for the MicroVM execution role (`<baseName>-microvm-execution-role`)

4. **Review test steps**:
   - Check for invalid instructions
   - Verify URLs are accessible
   - Test manually in browser first

### A step shows a VAR UNDEFINED_VALUE badge

**Symptoms**: In the **Execution Steps** table of a run, an instruction or the **Expected** value of a validation box
contains a badge `VAR UNDEFINED_VALUE` instead of a value. The step often failed, or Nova Act acted on the literal text
`{{<name>}}`.

**Cause**: The runner left `{{<name>}}` unresolved. It replaces only exact `{{name}}` tokens whose name it knows, and
leaves everything else as typed. The badge does not show the name; open the step in the use case's **Workflow Steps**
to see which token it is.

| Cause | How to tell | Fix |
|-------|-------------|-----|
| The variable was not defined when the run started | The name is missing from **Defined Variables** in the panel's **Variables** container (that list is the run's snapshot: application + use case + run overrides) | Define it on the use case (**Variables** tab), on the application, or pass `--var name=value`; then run again |
| Typo or different casing | The name differs from the defined key (`{{prodcut}}` vs `product`, `{{Product}}` vs `product`); names are case-sensitive | Correct the step instruction or validation value |
| Whitespace inside the braces | The step contains `{{ name }}`. Instructions and validation values only resolve `{{name}}` without spaces (transform arguments accept spaces, which is why the transform form shows `{{ variable }}`) | Remove the spaces |
| A `retrieve_value` / `transform` capture with that name never ran | A capture that has not run yet shows the variable name in italics, not `UNDEFINED_VALUE`. `UNDEFINED_VALUE` means no step of this run captures that name | Add the capture step before the step that uses it, or fix the `capture_variable` name |

Badges with an uppercase name (`VAR UNIQUE_ID`, `VAR TIMESTAMP`, `VAR EXECUTION_ID`, `VAR CREATED_AT`,
`VAR REPEAT_INDEX`, `VAR REPEAT_TOTAL`) are not errors: the runner fills these built-ins in itself, and the panel shows
their name instead of a value. A badge `VAR EMPTY_VALUE` is not an error either: the variable is defined, its value is
the empty string. See [Variables in the Execution Steps table](./user-guide.md#variables-in-the-execution-steps-table).

### MicroVM worker

Debugging is CloudWatch-only: the VM runs with the `NO_INGRESS` network connector and there is no shell. Everything the supervisor and the runner print goes to log group `/qa-studio/<baseName>/microvm`, stream `<execution_id>`. The AWS CLI (2.34 and earlier) has no `lambda-microvms` command; use boto3 (`boto3>=1.43.35`) for the runbook snippets below.

```python
import boto3
vms = boto3.client("lambda-microvms", region_name="<region>")
image_arn = "<worker stack output microvmImageArn>"
for vm in vms.list_microvms(imageIdentifier=image_arn)["items"]:           # paginate with nextToken if > 1 page
    print(vm["microvmId"], vm["state"], vm["startedAt"])              # PENDING, RUNNING, SUSPENDING, SUSPENDED, TERMINATING, TERMINATED
print(vms.get_microvm(microvmIdentifier="<microvmId>")["stateReason"])  # e.g. "Success."
vms.terminate_microvm(microvmIdentifier="<microvmId>")                 # stray VM; idempotent
```

#### Image build failed (`npm run deploy:worker` fails on `microvm_image`)

**Symptoms**: CloudFormation reports `CREATE_FAILED` / `UPDATE_FAILED` on `AWS::Lambda::MicrovmImage` after several minutes; `GetMicrovmImage` shows the latest version `FAILED`.

**Where the logs are**: log group `/qa-studio/<baseName>/microvm`, stream `<version>/<build-id>`. It contains the image build output *and* the supervisor's own stdout during the `/ready` / `/validate` probes (the platform POSTs `/ready` ~10 s after the supervisor starts and `/validate` ~20 s later).

**Causes**:
- A Dockerfile or `pip install` error — reproduce with a local `docker build -f web-app/worker/Dockerfile .` (the only place a local container tool is useful; the deploy itself needs none).
- `/ready` returned `503 {"status":"not_ready"}`: `qa-studio --help` failed inside the image (broken venv, import error). The stream shows the CLI's stderr.
- `ValidationException` on `environmentVariables`: a reserved key such as `AWS_REGION` was added to the image env (`lib/worker-stack.ts` `microvmEnvironment` deletes it on purpose).
- `ServiceQuotaExceededException` on the build: the regional *concurrent image builds* quota (5 in `eu-central-1`, 10 in `us-east-1`) or *100 images / 50 versions per image* is exhausted — delete old images or wait for running builds.

Fix the cause and redeploy; the zip (and the build) is re-created only when files under `web-app/worker/` or `qa-studio-cli/` change.

#### VM never reaches `RUNNING`, or `/run` failed

**Symptoms**: the execution stays `pending` (or `running` without steps progressing); the log stream named after the execution id contains `/run rejected (400|500): …` and `TerminateMicrovm(<id>) requested`, or nothing at all.

**Causes and fixes**:

| Log line | Meaning | Fix |
|---|---|---|
| `/run rejected (400): invalid runHookPayload` / `runHookPayload is N bytes; the limit is 4096 bytes` | The launcher's `RunPayload` does not match the image's model, or the payload is too large (very long mobile ARNs) | Redeploy so `lambdas/endpoints/run_payload.py` and `worker/supervisor_models.py` are the same version (`test_run_payload_parity.py`); shorten mobile fields |
| `/run rejected (500): image env for … is missing: X` | The MicroVM image was built without a required stack constant | Check `microvmEnvironment` in `lib/worker-stack.ts`; redeploy the worker stack |
| `/run rejected (500): SSM get_parameter failed` / `Secrets Manager read failed` | The VM execution role cannot read `/qa-studio/<baseName>/api-url`, `…/cognito-token-endpoint` or the M2M secret, or the api/auth stacks were not deployed | Deploy `api` and `auth` stacks; check the `microvm-execution-role` policies |
| `/run rejected (409)` | The platform delivered `/run` twice | Should not happen; the first child keeps running |
| no stream at all, `GetMicrovm` → `TERMINATED` with a non-`Success.` `stateReason` | The VM failed before the supervisor answered (platform error, `InsufficientCapacityException`) | Re-run; see quota section |

Every rejected `/run` self-terminates the VM. The execution record is not touched by the supervisor; within 5–10 minutes the reconciler marks it `failed` with `error_message: "reconciler: …"` (see next section). An execution that shows `failed` with the launch error text (`Failed to start MicroVM: …`) never got a VM at all: the `RunMicrovm` call itself failed in `execute_usecase` (its CloudWatch log has the exception).

#### Execution stuck in `running` / `pending`

**Expected behaviour**: a MicroVM execution cannot stay `running` forever. Three layers end it:

| Layer | When | Result on the record |
|---|---|---|
| Supervisor soft timeout | `maxExecutionDurationMinutes × 60 − 180 s` after launch | `failed`, `error_message: "timeout: run exceeded the configured ceiling of Ns"` (the runner reports it, browser torn down) |
| Platform `maximumDurationInSeconds` | `maxExecutionDurationMinutes × 60` | `/terminate` → SIGTERM → same `timeout:` report if the runner is still alive |
| Reconciler (`reconcile_executions`, every 5 min) | VM `TERMINATED` / not found, or `now > started_at + ceiling + 10 min` | `failed`, `error_message: "reconciler: <reason>"`; suite counters and cache cleanup as for any failure |

If an execution is still non-terminal 10 minutes after its VM disappeared, look at the `reconcile_executions` Lambda log and at the `QAStudio/Worker` metrics (`RunningMicrovms`, `ReconciledExecutions`). A record missing from `RUNNING_EXECUTIONS` (the launcher logged `Error recording running execution …`) is invisible to the reconciler: stop it through the UI / `POST …/stop`, which writes `stopped` and terminates the VM by `microvm_id`. The alarm on `ReconciledExecutions > 0` means a VM died without the runner reporting; treat every occurrence as a bug and read the execution's log stream.

#### `error_message: "reconciler: microvm TERMINATED"`

This is the reconciler's verdict, not the cause: the VM is gone and the runner never wrote a result. Open the execution's log stream (`cloudwatch_logs_url`; stream `<execution_id>` in `/qa-studio/<baseName>/microvm`) and look at the lines between `Spawning batch child` and `child_exit`:

| Log pattern | Cause | Fix |
|---|---|---|
| `Retryable 500 from GET …/usecase/{id}` repeated, then `ApiError: [500] Internal server error`, `child_exit … "exit_code": 2` within seconds of the spawn | **API throttling under suite fan-out.** The endpoint Lambdas have a small reserved concurrency (`lambdaConcurrency`); a suite starts ~20 VMs within seconds and every runner's first call is `GET /usecase/{id}`, so Lambda throttles (`Throttles` metric on `<baseName>-getusecase`, `Errors` stays 0) and API Gateway returns 500. | The CLI retries retryable responses (`429, 500, 502, 503, 504`, connection errors) 7 times with exponential backoff 1 → 16 s plus up to 3 s jitter (≈ 50–65 s in total; `API retry n/7 in Ns` in the log). If a run still exhausts that, the burst is longer than a minute: raise `lambdaConcurrency` or split the suite. |
| `/run rejected (400|500)` | supervisor could not start the child | see *VM never reaches RUNNING* |
| runner traceback, non-zero `exit_code`, no `PATCH …/status` | runner crashed before its first status write (import error, missing env, Nova Act startup) | the traceback names it |
| nothing after `Spawning batch child` | VM killed by the platform (`maximumDurationInSeconds` reached before the runner started, or `InsufficientCapacity`) | `GetMicrovm.stateReason` |

#### Quota exceeded: `ServiceQuotaExceededException`, `ThrottlingException`

| Error (in `execute_usecase` logs / the `500` body) | Quota | What to do |
|---|---|---|
| `ThrottlingException` on `RunMicrovm` | `RunMicrovm` rate 5/s, burst 5 (`L-535CA9B6` / `L-91B95582`) | Expected on a large suite fan-out. `microvm_launch.launch_microvm` retries 5 times with 1, 2, 4, 8 s backoff (`RunMicrovm throttled, retry n/5 in Ns` in the log). Only an execution that exhausts all retries is marked `failed` with `Failed to start MicroVM: … ThrottlingException`; rerun those use cases. For very large suites request a higher `RunMicrovm` rate. |
| `ServiceQuotaExceededException` on `RunMicrovm` | *Max allocated ARM_64 MicroVM memory* (`L-CD1C0CC4`, default 2048 GB per region; new accounts may be lower) across `RUNNING` + `SUSPENDED` VMs, 1 GB each | List VMs with the snippet above and terminate strays; check the reconciler is running (orphan VMs hold memory until `maximumDurationInSeconds`); request a quota increase in Service Quotas. |
| `ServiceQuotaExceededException` on the image build | concurrent image builds (5 eu / 10 us), 100 images, 50 versions per image | See *Image build failed*. |
| `InsufficientCapacityException` on `RunMicrovm` | none — the service has no free capacity in the region right now | Not retried by the launcher. The execution is marked `failed` with the error text; rerun later. Repeated occurrences: open an AWS support case. |

`maxExecutionDurationMinutes` above 480 is rejected at synth (`MAX_RUNTIME_MINUTES`); the platform ceiling is 8 h.

### AgentCore browser in a VPC

Applies to deployments with `vpcId` set ([Configuration → AgentCore browsers in a VPC](configuration.md#agentcore-browsers-in-a-vpc)). The run's log stream shows `Creating AgentCore browser: … network=VPC subnets=… security_groups=…` (batch) or `Network Mode: VPC` (wizard); `network=PUBLIC` means the image has no VPC settings — the last worker deploy was without `vpcId`, or the image rebuild (3–5 min after a VPC setting changes) has not finished.

| Symptom | Cause | Fix |
|---|---|---|
| Synth fails: `vpcId vpc-… has no private or isolated subnet in an AgentCore-supported Availability Zone` | None of the VPC's private/isolated subnets is in a supported AZ (public subnets are never picked automatically). The message lists the VPC's AZs and the supported ones. | Add a subnet in a supported AZ, or list suitable subnets in `vpcSubnetIds`. Compare AZ IDs with `aws ec2 describe-subnets --filters Name=vpc-id,Values=<vpcId> --query 'Subnets[].[SubnetId,AvailabilityZoneId]'`. |
| Synth fails: `vpcSubnetIds entry subnet-… is not a subnet of vpcId …` | Typo, or the subnet belongs to another VPC | Fix `vpcSubnetIds`; the message lists the VPC's subnets. After changing subnets in the account, delete the `vpc-provider:…` entry from `web-app/cdk.context.json` so CDK looks the VPC up again. |
| Synth fails: `vpcSubnetIds entry subnet-… is in Availability Zone …, which AgentCore does not support` | Explicit subnet in an unsupported AZ | Pick a subnet in one of the listed AZs. |
| Synth fails: `vpcId requires an explicit account/region` or `"aws ec2 describe-availability-zones" failed` | Synth ran without AWS credentials / AWS CLI | Run `npm run deploy` with credentials for the target account and region and the AWS CLI on the `PATH`. |
| Synth fails: `region "…" has no known AgentCore-supported Availability Zones` | Region missing from `AGENTCORE_SUPPORTED_AZ_IDS` | AgentCore VPC is not available there, or the table is out of date: update `web-app/lib/agentcore-az.ts` from the AgentCore VPC documentation. |
| Run fails: `AgentCore browser … ended in terminal status: FAILED` (or a `ValidationException` from `CreateBrowser`) | Subnet in an unsupported AZ (table out of date), security group in another VPC than the subnets, or the service-linked role `AWSServiceRoleForBedrockAgentCoreNetwork` is missing and cannot be created | Check the subnets and `workerSecurityGroupId` belong to `vpcId`; check the role exists in IAM (creating it needs `iam:CreateServiceLinkedRole` once per account). |
| Run fails: `AGENT_CORE_VPC=true but the following env vars are missing: …` | Local `qa-studio run --browser agentcore` with an incomplete env | Export `AC_VPC_ID`, `AC_SUBNET_IDS`, `AC_SECURITY_GROUP_ID` (see the [CLI README](../qa-studio-cli/README.md)), or unset `AGENT_CORE_VPC`. |
| Page load times out on the internal site | The target does not accept the browser: its security group lacks an inbound rule from the browser security group, the selected subnets have no route to it, or its host name does not resolve in the VPC | Allow inbound from the browser security group on the target; check route tables of the selected subnets; check the private hosted zone is associated with the VPC. |
| Public URL, external IdP login page, CDN assets do not load | No NAT route in the selected subnets — by design: the stack never adds NAT | Route the subnets through a NAT gateway, or keep tests on internal URLs. |
| Live view, recording or enterprise browser policy missing in an isolated subnet | Not yet verified whether these need a route out (design task 0) | Use subnets with a NAT route. |
| Deploy after removing `vpcId` (or changing `workerSecurityGroupId`) fails deleting the browser security group (`has a dependent object` / `DependencyViolation`) | AgentCore keeps browser ENIs up to 8 h after a browser is deleted | Retry the deploy later. `aws ec2 describe-network-interfaces --filters Name=group-id,Values=<sg-id>` shows the remaining ENIs. |
| `Configuration warning: agentCoreVPC is deprecated and ignored (…)` / `createVpcEndpoints …` | Old keys still in `configuration.json` | Remove them. `vpcId` with `agentCoreVPC: false` is an error — remove `agentCoreVPC`. |

### Cost allocation

Applies to the daily cost collector and the cost cards/tab in the UI ([Architecture → Cost allocation](architecture.md#cost-allocation), [Configuration → Cost allocation](configuration.md#cost-allocation)). The collector is the Lambda `<baseName>-costcollector` in the worker stack (no hyphen between "cost" and "collector" — the `createPythonLambda` naming; the EventBridge rule and the alarms are `<baseName>-cost-collector…`). Its log group is `/aws/lambda/<baseName>-costcollector`; every run ends with one JSON line whose `message.event` is `cost_collector.run`:

```
aws logs filter-log-events --log-group-name /aws/lambda/<baseName>-costcollector \
  --filter-pattern '{ $.message.event = "cost_collector.run" }' \
  --start-time $(( $(date +%s) - 86400 ))000 --query 'events[].message' --output text
```

The fields of that line (`days`, `billed_usd`, `allocated_usd`, `unallocated_usd`, `unmetered_usd`, `skipped_days`, `continued_with`, …) are listed in [Architecture → Collector run report](architecture.md#collector-run-report-and-events).

#### Re-run one or more days

Any day can be re-processed at any time; every write is idempotent and a re-run replaces the rows of exactly those dates in every ledger. Payloads are JSON, so pass `--cli-binary-format raw-in-base64-out` (AWS CLI v2 otherwise expects base64):

```bash
aws lambda invoke --function-name <baseName>-costcollector \
  --cli-binary-format raw-in-base64-out \
  --payload '{"days":["2026-11-03"]}' out.json && cat out.json
```

`out.json` is the run report (same fields as the log line). Several days: `{"days":["2026-11-02","2026-11-03"]}`. Days must be before today (UTC) and `days` cannot be combined with `from`/`to`; otherwise the function fails with a `ValueError` naming the field, and `out.json` holds `{"errorMessage": …}`.

#### Backfill a range

```bash
aws lambda invoke --function-name <baseName>-costcollector \
  --cli-binary-format raw-in-base64-out \
  --payload '{"from":"2026-10-01","to":"2026-10-31"}' out.json && cat out.json
```

The range is processed oldest day first. When fewer than 60 s of the 15-minute budget remain, the run stops starting new days, lists them under `skipped_days` with `reason: "deadline"`, hands them to a fresh asynchronous invocation of itself and reports them under `continued_with`. Watch the `cost_collector.run` log lines until one arrives with an empty `continued_with` and no `deadline` entries — that is the end of the backfill. Scheduled runs never self-continue (the next schedule covers what was skipped). Backfill reach is bounded by Cost Explorer's 13 months of history and by the use-case metadata that still exists (deleted use cases land in `unallocated`). Compute seconds for executions that finished before `microvm_started_at` / `microvm_terminated_at` existed on the execution record are metered by wall-clock (`compute_wallclock_fallbacks` in the report) — that history cannot be made more precise.

**Cost of a backfill is set by the oldest day, not by the number of days.** `ListActs` has no date filter: the collector pages every workflow definition's acts from the newest one back to the oldest requested day. Asking for one month five months ago therefore reads five months of acts — as much as asking for the whole five months. Prefer one range that covers everything you need (`from` = oldest day, `to` = yesterday) over several small ranges in the past; a second run over the same old range costs the same again. Definitions are paged concurrently (`NOVA_ACT_LIST_WORKERS`, default 8, ≈ 2–3 min for 11 months of the dev account's history), and a `nova_act progress: N/M definitions, …` line is logged every 25 definitions. If the pass still cannot finish within the budget, the run fails with `UsageDeadlineExceeded: nova_act: usage pass exceeded its time budget after N/M units` (all days listed under `skipped_days` with `reason: "deadline"`, nothing written, no self-continuation because the same range cannot succeed): narrow the range so it ends closer to today, or raise `NOVA_ACT_LIST_WORKERS` on the function.

#### Interpreting the numbers

| Figure | Where | Meaning | Action |
|---|---|---|---|
| `summary: null` / *No cost data yet* in the UI, `—` on the dashboard | API, UI | The dimension has no `USAGE#… / SUMMARY` item: the collector has not run yet, `costAllocation.enabled` is `false`, or the use case/application had no usage on any processed day. | Wait for the next schedule, or run a day manually. Check the `<baseName>-cost-collector-errors` alarm. |
| `unassigned` (overall `buckets`) | Ledger rows, run report | Cost of use cases without an `application_id`. In the overall total, in no application. | Assign the use cases to applications (the roll-up changes from that day on; history is not rewritten). |
| `unallocated` (overall `buckets`, `unallocated_usd`) | Ledger rows, run report | Usage of Nova Act workflow definitions that are not a use case (any more): deleted use cases whose definition still has acts, plus acts without `endedAt`. | Expected after deleting use cases; nothing to do. A persistently large share with no deletions means use-case ids and workflow names have diverged — check `workflow_manager.ensure_workflow`. |
| `unmetered` (`unmetered_usd`) | Ledger rows, run report, alarm | Bill without measured usage: `billed − Σ allocated` per source. Normal causes: rounding; executions still running at collection time (`compute_running_executions`); cloud sessions that launched a VM but never issued a Nova Act act (the compute source only queries use cases Nova Act saw that day — see [Architecture → known limitation](architecture.md#cost-allocation)). | Small amounts are normal and shrink when the lookback re-processes the day. The `<baseName>-cost-collector-unmetered` alarm fires when it exceeds half the bill — see below. |
| `estimated: true` on a row, `estimated_days > 0`, *(estimated)* in the card footer | Ledger, API, UI | Cost Explorer still marks that day as estimated and may revise it. In practice this lasts about four days. | Nothing. The default `lookbackDays: 3` re-processes D-1 … D-3 nightly; raise it to `5` to pick up the last revisions. |
| `list_cost` is `0` for `compute` | Ledger, API | By design: MicroVM list prices are per vCPU-second / GB-second of a VM size the collector does not know. | — |
| `window_30d_trend: null` / *not enough data* | API, UI | Fewer than `2 × window` days of data (`days_available`). The 30-day trend needs 60 days. | Wait, or backfill (see above) if Cost Explorer history exists. |
| A use case's 30-day figure dropped to a few days' worth after it was moved to another application | API, UI | Its ledger restarted under the new application's folder; the old file stays under the old application as history and is not read. | Expected (design decision 4a). |

#### `skipped_days` with `reason: "cost_explorer_unavailable"` — all days skipped, nothing written

**Cause**: Cost Explorer answered `DataUnavailableException`. On a brand-new account Cost Explorer must be **enabled once** in the console (Billing → Cost Explorer); the API returns data about 24 hours later. In a member account of an AWS Organization, `ce:GetCostAndUsage` only works when the management account has enabled member access to Cost Explorer. **Fix**: enable Cost Explorer / member access, then re-run the skipped days with `{"days": [...]}`. Until then every scheduled run skips its days and writes nothing (the run itself succeeds, so the errors alarm does not fire — watch the log line).

#### Cost card shows "Failed to fetch … costs: … AccessDenied … s3:ListBucket"

**Symptom**: `GET /usecase/{id}/costs` or `GET /applications/{id}/costs` answers `500` with `An error occurred (AccessDenied) when calling the GetObject operation: User: …/<baseName>-applicationrouter is not authorized to perform: s3:ListBucket on resource: arn:aws:s3:::…-artefacts-…`. The Cost card or the Cost tab shows a red error Alert instead of *No cost data yet*. It happens for a use case or application that has no ledger file yet (it never ran, or the collector has not processed its first usage). `GET /dashboard/costs` reads only SUMMARY items and is not affected. **Cause**: when the caller has no `s3:ListBucket` on the bucket, S3 reports a missing object as `403 AccessDenied` instead of `404 NoSuchKey`. `cost_ledger.read` maps only `NoSuchKey` to an empty ledger, so the handler answers `500`. The application router role lacked that grant. **Fix**: the router's inline policy (`web-app/lib/lambda-stack.ts`) needs `s3:ListBucket` on the artefacts bucket ARN, limited to `s3:prefix = cost_allocation/*` (the statement the collector has), next to `s3:GetObject` on `cost_allocation/*`. Redeploy the lambdas stack with `npm run deploy:lambdas`. The routes then return `200` with `summary: null` and `days: []`. Do not treat `AccessDenied` as "empty" in code: that would hide a broken grant behind *No cost data yet*.

#### Alarm `<baseName>-cost-collector-errors`

Lambda `Errors ≥ 1` over one day: the run raised, the ledgers of its days were **not** updated. Open the Lambda's log, fix the cause, re-run the days with `{"days": [...]}`. Typical causes: `AccessDeniedException` on `ce:GetCostAndUsage` / `nova-act:ListActs` (IAM, or Cost Explorer member access missing — that one surfaces as `DataUnavailableException`, see above), `ValueError` from the Pricing lookup (`expected exactly one OnDemand dimension with unit 'Second'` — the Nova Act price list changed shape), `BatchGetItem still has N unprocessed use-case keys`, or a `412`/`ConditionalRequestConflict` loop on a ledger (another writer kept changing the file — a manual run overlapping the scheduled one; re-run).

#### Alarm `<baseName>-cost-collector-unmetered`

Metric filters on the `cost_collector.run` log line publish `BilledUsd` and `UnmeteredUsd` (Sum per day) to the CloudWatch namespace `QAStudio/CostAllocation`; the alarm's metric-math expression `IF(unmetered > 0.5 * billed, 1, 0)` breaches when more than half of a run's bill could not be matched to any measured usage. Causes, in order of likelihood: (1) Nova Act saw no acts for the day although it was billed — `definitions`/`pages` in the report are 0 or tiny: the collector's `nova-act:ListWorkflowDefinitions` permission or the `us-east-1` endpoint is wrong, or the workflow definitions were deleted; (2) `costAllocation.novaActServiceName` / `compute.ceService` / the usage-type prefixes do not match what Cost Explorer bills under in this account (`aws ce get-cost-and-usage … --group-by Type=DIMENSION,Key=SERVICE` lists the service strings; the spike found `NovaAct` and `AWS Lambda`); (3) many executions were still running at 06:00 UTC (`compute_running_executions`) — the lookback re-processes the day and the alarm clears. The alarm is per run, so one noisy day resolves itself the next morning; a standing alarm needs (1) or (2) fixed and the days re-run.

#### Reading the ledgers directly

The ledgers are plain NDJSON in the artefacts bucket of the default region, prefix `cost_allocation/` (`overall.ndjson`, `{application_id}/raw.ndjson`, `{application_id}/{usecase_id}.ndjson`, `_unassigned/{usecase_id}.ndjson`); they need S3 read access, not an API token:

```bash
aws s3 cp s3://<account>-<baseName>-artefacts-<region>/cost_allocation/overall.ndjson - | tail -n 3 | jq .
```

Never edit a ledger by hand: the collector rewrites the processed dates on every run and a row with a duplicate date makes `summarize` raise.

### Artifacts Not Loading

**Symptoms**:
- Videos/screenshots show "Access Denied"
- Artifacts missing from execution details

**Solutions**:

1. **Check S3 bucket permissions**:
   - Verify bucket policy allows CloudFront access
   - Check CORS configuration

2. **Verify presigned URLs**:
   - URLs expire after 1 hour
   - Refresh the page to get new URLs

3. **Check artifact upload**:
   - Review worker logs for upload errors
   - Verify S3 bucket exists and is accessible

---

## CLI Issues

### Installation Fails

**Symptoms**:
- `pip install` fails with errors
- Import errors when running commands

**Solutions**:

1. **Check Python version**:
   ```bash
   python3 --version  # Should be 3.11+
   ```

2. **Use virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -e ./qa-studio-cli
   ```

3. **Install runner dependencies** (for local execution):
   ```bash
   pip install -e "./qa-studio-cli[runner]"
   ```

4. **Check for conflicting packages**:
   ```bash
   pip list | grep qa-studio
   # Uninstall old versions if found
   pip uninstall qa-studio-cli
   ```

### Authentication Fails

**Symptoms**:
- `qa-studio login` fails
- Browser doesn't open
- "Invalid credentials" error

**Solutions**:

1. **Verify configuration**:
   ```bash
   qa-studio status
   # Check API URL, Cognito domain, client ID
   ```

2. **Reconfigure**:
   ```bash
   qa-studio configure
   # Enter correct values
   ```

3. **Check network connectivity**:
   ```bash
   # Test if you can reach Cognito
   curl https://{domain}.auth.{region}.amazoncognito.com/.well-known/openid-configuration
   ```

4. **Clear cached tokens**:
   ```bash
   rm ~/.qa-studio/tokens.json
   qa-studio login
   ```

5. **Check firewall/proxy**:
   - Ensure outbound HTTPS (port 443) is allowed
   - Configure proxy if needed

### Local Test Execution Fails

**Symptoms**:
- `qa-studio run` command fails
- "Module not found" errors
- Browser fails to start

**Solutions**:

1. **Install runner dependencies**:
   ```bash
   pip install -e "./qa-studio-cli[runner]"
   ```

2. **Check Nova Act SDK installation**:
   ```bash
   python3 -c "import nova_act; print(nova_act.__version__)"
   ```

3. **Verify Playwright installation**:
   ```bash
   playwright install chromium
   ```

4. **Check AWS credentials** (for Bedrock access):
   ```bash
   aws configure list
   # Ensure credentials are configured
   ```

5. **Enable debug logging** (the API calls and Nova Act trace are only shown with `--verbose`):
   ```bash
   qa-studio run --usecase-id test-123 --verbose
   ```

### Command Not Found

**Symptoms**:
- `qa-studio: command not found`

**Solutions**:

1. **Verify installation**:
   ```bash
   pip show qa-studio-cli
   ```

2. **Check PATH**:
   ```bash
   # Find where pip installs scripts
   python3 -m site --user-base
   
   # Add to PATH if needed
   export PATH="$PATH:$(python3 -m site --user-base)/bin"
   ```

3. **Use python -m**:
   ```bash
   python3 -m qa_studio_cli --help
   ```

4. **Reinstall in editable mode**:
   ```bash
   pip install -e ./qa-studio-cli
   ```

---

## API Issues

### 401 Unauthorized

**Symptoms**:
- API requests return 401
- "Invalid token" error

**Solutions**:

1. **Re-authenticate**:
   ```bash
   qa-studio logout
   qa-studio login
   ```

2. **Check token expiration**:
   - Access tokens expire after 1 hour
   - CLI automatically refreshes tokens
   - If refresh fails, login again

3. **Verify OAuth client**:
   - Check client exists in web UI
   - Verify client has required scopes

### 403 Forbidden

**Symptoms**:
- API requests return 403
- "Missing required scopes" error
- CLI returns `403 Insufficient permissions.` with **no error detail**

**Solutions**:

1. **Check that `api_url` includes the `/api` base path** (most common cause of a
   detail-less 403 from the CLI):
   - Your `api_url` must end with `/api` — for example
     `https://<api-id>.execute-api.<region>.amazonaws.com/api/` or
     `https://<cloudfront-domain>/api`.
   - If you omit `/api` (e.g. the bare CloudFront URL), requests route to the
     web-app origin instead of the API and return a bodyless 403 that the CLI
     renders as `403 Insufficient permissions.` with no further detail.
   - Check and fix with:
     ```bash
     qa-studio status          # inspect the configured API URL
     qa-studio configure       # re-enter it with the /api suffix
     ```

2. **Check user permissions**:
   - Verify user has access to the resource
   - Check Cognito group memberships

3. **Verify OAuth scopes**:
   - For CLI: User must have appropriate permissions
   - For API clients: Client must have required scopes

4. **Contact administrator**:
   - Request access to the resource
   - Or create new OAuth client with correct scopes

### 404 Not Found

**Symptoms**:
- Resource not found errors
- Invalid ID errors

**Solutions**:

1. **Verify resource exists**:
   - Check ID is correct
   - Verify resource wasn't deleted
   - Check you have access to the resource

2. **Check API endpoint**:
   ```bash
   qa-studio status
   # Verify API URL is correct
   ```

### 500 Internal Server Error

**Symptoms**:
- API returns 500 error
- Unexpected errors

**Solutions**:

1. **Retry the request**:
   - Temporary issues often resolve automatically

2. **Check CloudWatch logs**:
   - AWS Console → CloudWatch → Log Groups
   - Look for Lambda function errors

3. **Contact support**:
   - Provide error details
   - Include request ID if available

---

## Mobile Testing Issues

### Device Farm Session Fails to Start

**Symptoms**:
- "Session failed to reach RUNNING state after 300 seconds"
- "Unknown error with device"

**Solutions**:

1. **Try a different device**: Some devices may be temporarily unavailable. Use auto-selection (leave device_arn empty) or pick a device marked "Highly available" in the device picker.

2. **Check Device Farm service status**: Visit the AWS Console → Device Farm → us-west-2 to verify the service is operational.

3. **Verify app binary compatibility**: Ensure the `.ipa`/`.apk` is compatible with the selected device's OS version. Older devices may not support newer app formats.

### App Not Found on Device

**Symptoms**:
- "App with bundle identifier 'com.example.app' unknown"
- App fails to launch after session starts

**Solutions**:

1. **Verify app binary was uploaded**: Check that the use case has an app binary uploaded via the web UI, or use `--app-path` with the CLI.

2. **Check app identifiers**: Ensure `app_package`/`app_activity` (Android) or `bundle_id` (iOS) match exactly what's in the app binary.

3. **Re-upload the binary**: The Device Farm upload may have expired. Upload a fresh copy via the web UI or CLI.

### Session Recording Not Available

**Symptoms**:
- "Failed to load recording" in the UI
- Recording section shows error after test completes

**Solutions**:

1. **Wait 5-10 minutes**: Device Farm recordings are downloaded asynchronously. The recording Lambda retries every 3 minutes for up to 30 minutes.

2. **Check the recording download Lambda logs**: In CloudWatch, look for the `download_device_farm_recording` Lambda to see if it's retrying or encountered an error.

3. **Verify IAM permissions**: The recording Lambda needs `devicefarm:ListArtifacts` and `devicefarm:GetRemoteAccessSession` permissions.

### iOS Typing Fails

**Symptoms**:
- "iOS mobile: type fallback failed"
- Text input doesn't work on iOS devices

**Solutions**:

1. **Retry the test**: This can be a transient Appium/XCUITest issue.

2. **Simplify the step instruction**: Instead of "Type 'JFK' in the search field", try "Tap the search field and enter JFK".

3. **Check the device OS version**: Some XCUITest commands behave differently across iOS versions.

---

## Repeat Step Issues

### Later rows of a repeat stay `pending`

**Symptoms**: An execution with a repeat step fails on `Row 2/3`; the steps tagged `Row 3/3` never ran and stay `pending`.

**Cause**: This is by design (fail-fast). The first failing expanded step marks the execution failed and execution stops; later rows are not attempted. Continue-to-next-row is not available in v1.

**Solutions**:
1. Open the failed step — the `Row i/n` badge and row header tell you which dataset row broke the flow.
2. Fix the row's data (or the flow) and rerun. In CI you can feed a corrected CSV with `qa-studio run --dataset-file`.
3. If only one row matters, run with a one-row CSV.

### Trajectory replay is never used inside a repeat

**Symptoms**: Steps inside a repeat always run through Nova Act even though the use case has `enable_cache` on and other steps show "Executed from cache".

**Cause**: Expanded steps share their definition `step_id` across all rows and their instruction differs per row after `{{column}}` substitution, so a recording from one row would be replayed against another. Replay and save are deliberately disabled for steps that carry `repeat_row_index`.

**Solutions**: None needed — this is expected. Keep setup steps that benefit from caching (login, navigation to the entry page) *outside* the repeat where possible.

### `400` when executing: "repeat ... has no steps inside" / "has no rows"

**Cause**: A repeat step was saved without children or without rows. The execute endpoints refuse to create a half-usable execution.

**Solutions**: Add at least one step inside the repeat (**Add step inside**) and at least one row, or delete the repeat.

### `--dataset-file` exits with code 2

**Cause**: Usage error before any browser starts — file not found, empty CSV, header columns ≠ the repeat's columns, unknown `LABEL`, more than one repeat without a `LABEL=`, used with `--suite-id` / `--execution-id`, or caps exceeded (100 rows, 20 columns, 200 KB).

**Solutions**: Make the header row exactly the repeat's columns (any order) and address the repeat by its label (`--dataset-file "Login as each user=users.csv"`). For a repeat that references an application dataset, the columns are the dataset's columns (`qa-studio apps datasets get <app-id> <dataset-id>`).

---

## Application Configuration Issues

Variables, secrets and datasets defined on an application are inherited by its use cases (precedence: application < use case < CLI override). See [User Guide → Applications](./user-guide.md#applications-shared-variables-secrets-and-datasets).

### `400` when executing: `{"error": "dataset not found", "dataset_id": "…"}`

**Symptoms**: **Trigger Execution**, `POST /usecase/{id}/execute`, a suite run or a schedule fails with `dataset not found` (the suite endpoint adds `details.usecase_id`). No execution record is created.

**Cause**: A repeat step references an application dataset (`dataset_id`) that no longer exists in the use case's application — the dataset was deleted by someone with API access while the step still pointed at it, the use case was re-created in another application from an export, or the use case has no application at all.

**Solutions**:
1. Open the repeat step in **Workflow Steps**: its summary reads *Application dataset (not loaded)* when the reference is dangling. Edit the step, pick an existing dataset under **Dataset source → Application dataset**, or switch to **Inline** and paste the rows.
2. Or re-create the dataset on the application (**Applications → app → Datasets → Create dataset**, or `qa-studio apps datasets create`) and repoint the step — dataset ids are generated, so the new dataset has a new id.
3. In CI a `--dataset-file "<label>=rows.csv"` override does **not** bypass this check: the reference is resolved first.

### `qa-studio run --local-only` exits 2: `dataset <id> not found in application <app>` or the `api/applications.read` hint

**Cause**: In local-only mode the CLI fetches the referenced dataset through `GET /applications/{id}/datasets/{datasetId}`. The error names the missing dataset; `cannot read dataset …: 403 … --local-only with application datasets needs the api/applications.read scope` means the token lacks the scope. User tokens (`qa-studio login`) carry it for every team role; OAuth client tokens do **not** — the CLI's client-credentials request asks for a fixed scope list without it (`qa_studio_cli/auth/client_credentials.py`).

**Solutions**: Run in remote mode (drop `--local-only`; the server resolves the dataset and the executing identity needs only `api/usecases.execute`), use a user token for local-only runs, or fix the dangling reference as above. See [CI/CD Integration → Application-level configuration](./ci-cd-integration.md#application-level-configuration-variables-secrets-datasets).

### `409` when deleting a dataset: "Dataset is still in use"

**Symptoms**: **Delete** on the application's Datasets page shows *Dataset is still in use* with a list of use cases; the API returns `409 {"error": "dataset is referenced by repeat steps of this application; remove the references first", "usecases": [{"usecase_id", "name"}]}`; `qa-studio apps datasets delete` prints *Referenced by* and the use cases.

**Cause**: At least one repeat step of the listed use cases carries this `dataset_id`. The check is deliberate — deleting the dataset would make those use cases fail at execution with `dataset not found`.

**Solutions**: Follow the links in the notice, edit each listed repeat step and switch it to **Inline** rows or another dataset, then delete again.

### `409` when adding a use case to an application: "use case references application datasets"

**Symptoms**: **Add existing usecases** on an application (or `POST /applications/{id}/usecases`) fails with `409 {"error": "use case references application datasets", "usecases": [{"usecase_id", "name", "steps": [{"id", "instruction"}]}]}`. Nothing is moved.

**Cause**: A use case being moved in has repeat steps that reference datasets of the application it is leaving; dataset ids are scoped to one application, so the reference would dangle after the move.

**Solutions**: Switch the listed steps to inline rows (or re-create the dataset in the target application and repoint them after the move), then add the use case again. Variables and secrets move silently; a key that only existed on the old application fails the next run with the usual *unresolved variable* / *secret not found* error — define it on the new application or the use case.

### `409` when creating or renaming a dataset

**Cause**: `a dataset named "<name>" already exists in this application` — names are unique per application, case-insensitive.

**Solutions**: Pick another name or edit the existing dataset.

### Import fails with `dataset not found in this application`

**Symptoms**: `qa-studio tests import` (or `POST /import`, `POST /usecase/{id}/clone`) returns `400 {"success": false, "error": "dataset not found in this application", "datasetIds": ["…"]}`.

**Cause**: The export JSON keeps `dataset_id` on repeat steps (rows are never inlined). The target application has no dataset with that id — typically because the file came from another application or environment.

**Solutions**: Import into the original application, or edit the step in the file: replace `dataset_id` with `repeat_columns` / `repeat_rows` (e.g. from `qa-studio apps datasets get <app-id> <dataset-id> --output json`), or create the dataset in the target application and put its new id into the file.

### Inherited values are missing or wrong

| Symptom | Explanation |
|---|---|
| A use-case **Variables** card shows a row with an *Application* badge that cannot be edited or deleted | Inherited application variable. Change it on **Applications → app → Variables**, or add a use-case variable with the same key to override it for this use case only. |
| Overriding a key with a use-case variable did not take effect | Check for a `--var KEY=VALUE` on the run — the CLI layer wins over both the application and the use case. |
| A secret step typed the wrong value | A use-case secret with the same key shadows the application secret. `GET /usecase/{id}/secrets` shows both with `source`; the value-access log line (`secret_value_access … source=usecase\|application`) shows which layer answered. |
| `GET /usecase/{id}/executions/{eid}/variables` lists only the use case's own variables in `variables` | `variables` is the use case's **current** `USECASE_VARIABLES` record, kept for compatibility. Read `execution_variables` instead: the snapshot of the merged variables (application + use case + overrides) the run started with. The web UI's **Defined Variables** list and the step badges use it. |
| The Variables / Secrets / Datasets pages are read-only for me | The web UI lets only the Team Lead of the owning team (or an Admin) edit them; Editors can write through `qa-studio apps …` or the API with `api/applications.write`. See [User Management](./user-management.md#application-management). |

---

## Performance Issues

### Slow Test Execution

**Symptoms**:
- Tests take longer than expected
- Timeouts occur frequently

**Solutions**:

1. **Check target application performance**:
   - Test manually in browser
   - Verify application is responsive

2. **Optimize test steps**:
   - Remove unnecessary waits
   - Use more specific selectors
   - Reduce number of steps

3. **Check network latency**:
   - Test from same region as target application
   - Verify network connectivity

4. **Review Nova Act model**:
   - Try different model if available
   - Check Bedrock service limits

### High AWS Costs

**Symptoms**:
- Unexpected AWS bills
- High MicroVM or Bedrock costs

**Solutions**:

1. **Review execution frequency**:
   - Reduce unnecessary test runs
   - Use test suites instead of individual tests

2. **Lower `maxExecutionDurationMinutes`** (MicroVM): a hung run is billed until the ceiling; 60 min is the default.

2. **Optimize test suites**:
   - Remove duplicate tests
   - Combine similar tests

3. **Check artifact retention**:
   - Configure S3 lifecycle policies
   - Delete old artifacts

4. **Monitor usage**:
   - Set up CloudWatch alarms
   - Review Cost Explorer regularly
   - Use the per-use-case and per-application cost cards in QA Studio to find the tests that drive the bill (collected daily; see [Cost allocation](#cost-allocation) above for the runbook)

---

## Debug Mode

### Enable Debug Logging

**Web Application**:
- Open browser developer console (F12)
- Check Console tab for errors
- Check Network tab for API requests

**CLI**:
```bash
qa-studio run --usecase-id test-123 --verbose
```

The default console output is only the progress lines (one per test, one per step) plus warnings and errors. `--verbose` is required to see the API calls (`→ GET https://…`), the engine internals and Nova Act's think/act trace on the console. The per-execution log artifact (`/tmp/qa-studio-artifacts/<usecase-id>/logs.txt` for local runs — the path is reported as `artifacts.logs` in the JSON result; `logs.txt` uploaded with the execution in remote mode) always contains the full DEBUG log, with or without the flag.

**Worker Logs**:
- Follow the **CloudWatch Logs** link on the execution detail page (`cloudwatch_logs_url`), or:
- CloudWatch → log group `/qa-studio/<baseName>/microvm` → stream `<execution_id>` (wizard sessions: `<session_id>`; image builds: `<version>/<build-id>`). The VM has no shell and no ingress; this stream is the only debugging channel.

### What logs never contain

Logs are designed to be safe to share. Even in debug mode:

| Source | Never logged | Logged instead |
|---|---|---|
| CLI runner (console, `logs.txt`, `suite_logs.txt`) | API response bodies, resolved secret values, bearer tokens/JWTs, STS session tokens, SigV4 signatures | Response status and size; masked values appear as `***` |
| CLI runner — AWS SDK / HTTP libraries (`botocore`, `boto3`, `urllib3`, `s3transfer`) | Anything below `WARNING` | Warnings and errors only |
| API Lambdas | Raw API Gateway events (headers, `Authorization`, request bodies) | `request_log_summary`: method, resource, path/query parameter *names*, request ID, caller `sub` or client ID, body size |
| Lambda authorizer / pre-token trigger | Tokens, decoded claims, email, username | Token use, `sub` / client ID, groups, resolved scopes |
| Worker secrets client | Secret values and full secret paths | Secret key name and error type |

If you need full HTTP traces for a CLI issue, reproduce it locally against a test use case with throwaway secrets.

### Common Log Patterns

**Successful Execution**:
```
INFO: Fetching test steps...
INFO: Executing step 1: Navigate to login page
INFO: Step completed successfully
INFO: Executing step 2: Enter credentials
INFO: Step completed successfully
INFO: Execution completed: success
```

**Authentication Error**:
```
ERROR: Authentication failed: Invalid credentials
```

**API Error**:
```
ERROR: API request failed: 404 - Resource not found
```

**Network Error**:
```
ERROR: Connection timeout: Unable to reach API endpoint
```

---

## Getting Help

### Support Channels

- **GitHub Issues**: [Report bugs and request features](https://github.com/aws-samples/sample-nova-act-qa-studio/issues)
- **Documentation**: [Complete documentation](../README.md)
- **AWS Support**: For AWS service issues

### Information to Provide

When requesting support, include:

1. **Error message**: Full error message from logs
2. **Steps to reproduce**: What you were trying to do
3. **Environment**: OS, Python version, browser
4. **Logs**: Relevant logs with sensitive data redacted
5. **Configuration**: API endpoint, region (no secrets!)

**Example**:
```
Subject: CLI authentication failing

Description:
I'm unable to authenticate with the CLI. The browser opens but returns an error.

Error message:
ERROR: Authentication failed: Invalid redirect URI

Environment:
- OS: macOS 14.0
- Python: 3.11.5
- CLI version: 1.0.0

Steps to reproduce:
1. Run `qa-studio configure`
2. Enter API URL and Cognito domain
3. Run `qa-studio login`
4. Browser opens but shows error

Configuration:
- API URL: https://api.example.com
- Cognito domain: myapp.auth.us-east-1.amazoncognito.com
- Client ID: 7abc123def456

I've verified:
- API URL is correct
- Cognito domain is correct
- Client ID exists in Cognito
```

---

## Frequently Asked Questions

### How do I reset my password?

Use the "Forgot password" link on the login page, or contact your administrator.

### Can I run tests locally without cloud execution?

Yes, use `qa-studio run --usecase-id test-123 --local-only`

### How do I share tests with my team?

Export tests as JSON and share the file, or grant team members access to your QA Studio instance.

### What browsers are supported?

QA Studio uses Chromium via Playwright. Other browsers are not currently supported.

### How do I handle dynamic content?

Use appropriate wait conditions in your test steps, or add explicit wait steps.

### Can I run tests in parallel?

Yes, test suites execute tests in parallel automatically. For CLI, run multiple commands in separate terminals.

### How long are artifacts retained?

Configure S3 lifecycle policies to set retention period. Default is indefinite.

### Can I use custom domains?

Yes, configure a custom domain for CloudFront in the CDK stack.

### How do I backup my tests?

Export tests as JSON files regularly, or enable DynamoDB point-in-time recovery.

### What's the maximum test size?

No hard limit, but we recommend keeping tests focused and under 20 steps each.
