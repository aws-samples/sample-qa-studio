# Nova Act GA Cross-Region Architecture Specification

## Executive Summary

Migration from Nova Act Preview API to GA service requires cross-region architecture due to GA service availability only in **us-east-1**, while your application runs in **eu-central-1**.

**Current State:** Preview API (region-agnostic) → **Target State:** GA Service (us-east-1 only)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          EU-CENTRAL-1 (Primary)                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐          │
│  │   Frontend   │──────│   API GW     │──────│   Lambda     │          │
│  │   (React)    │      │              │      │   (Go)       │          │
│  └──────────────┘      └──────────────┘      └──────────────┘          │
│                                                      │                   │
│                                                      ▼                   │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │                      DynamoDB Table                           │      │
│  │  - Executions, Steps, Workflows, Commands                    │      │
│  └──────────────────────────────────────────────────────────────┘      │
│                                                      │                   │
│                                                      ▼                   │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │                    EventBridge Bus                            │      │
│  │  - Triggers: execution_started, step_command                 │      │
│  └──────────────────────────────────────────────────────────────┘      │
│                                                      │                   │
│                                                      ▼                   │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │              ECS Fargate Worker (Wizard Mode)                 │      │
│  │  - Browser automation via DCV                                 │      │
│  │  - Polls DynamoDB for commands                                │      │
│  │  - Executes steps via Nova Act SDK                            │      │
│  │  - Stores artifacts in S3 (eu-central-1)                      │      │
│  └──────────────────────────────────────────────────────────────┘      │
│                                │                                         │
│                                │ Cross-Region SDK Call                  │
│                                ▼                                         │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │         S3 Bucket (eu-central-1) - Primary Artifacts          │      │
│  │  - Browser recordings, screenshots, logs                      │      │
│  │  - Replication source for us-east-1                           │      │
│  └──────────────────────────────────────────────────────────────┘      │
│                                │                                         │
│                                │ S3 Cross-Region Replication            │
│                                ▼                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                 │
                                 │ HTTPS/TLS 1.2+
                                 │
┌─────────────────────────────────────────────────────────────────────────┐
│                           US-EAST-1 (Nova Act)                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │         S3 Bucket (us-east-1) - Nova Act Artifacts            │      │
│  │  - Workflow definitions                                       │      │
│  │  - Execution traces and metadata                              │      │
│  │  - Replicated artifacts from eu-central-1                     │      │
│  │  Bucket: <account>-nova-act-qa-studio-modular-artefacts-     │      │
│  │          us-east-1                                            │      │
│  └──────────────────────────────────────────────────────────────┘      │
│                                │                                         │
│                                ▼                                         │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │                  Nova Act GA Service                          │      │
│  │                                                                │      │
│  │  Control Plane APIs:                                          │      │
│  │  - CreateWorkflowDefinition (requires S3 bucket)              │      │
│  │  - GetWorkflowDefinition                                      │      │
│  │  - ListWorkflowDefinitions                                    │      │
│  │  - DeleteWorkflowDefinition                                   │      │
│  │                                                                │      │
│  │  Data Plane APIs:                                             │      │
│  │  - CreateWorkflowRun                                          │      │
│  │  - CreateSession                                              │      │
│  │  - CreateAct                                                  │      │
│  │  - InvokeActStep                                              │      │
│  │  - UpdateAct                                                  │      │
│  │  - GetWorkflowRun                                             │      │
│  │  - ListWorkflowRuns                                           │      │
│  └──────────────────────────────────────────────────────────────┘      │
│                                                                           │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │              CloudWatch Metrics (Optional)                    │      │
│  │  - Invocations, Latency, Errors, Throttles                   │      │
│  └──────────────────────────────────────────────────────────────┘      │
│                                                                           │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Options

### Option 1: SDK-Based Integration (Recommended)

**Description:** Worker code uses Nova Act SDK with AWS IAM authentication, SDK makes cross-region calls to us-east-1.

**Pros:**
- Minimal infrastructure changes
- Leverages existing worker architecture
- SDK handles API complexity
- No additional AWS services required

**Cons:**
- Cross-region latency (~80-120ms EU→US)
- Worker must have us-east-1 IAM permissions
- SDK version dependency

**Implementation:**
```python
# worker/wizard_worker.py modifications
from nova_act import NovaAct, workflow

# Initialize with workflow definition (us-east-1)
@workflow(
    workflow_definition_name="qa-studio-wizard",
    model_id="nova-act-latest",
    region="us-east-1"  # Explicit region
)
def execute_wizard_workflow(starting_url: str, steps: list):
    with NovaAct(
        starting_page=starting_url,
        headless=True,
        tty=False
    ) as nova:
        for step in steps:
            nova.act(step.instruction)
```

---

### Option 2: Dual-Region Deployment

**Description:** Deploy Nova Act workflow execution infrastructure in us-east-1, keep orchestration in eu-central-1.

**Pros:**
- Lower latency for Nova Act operations
- Better observability in us-east-1
- Separation of concerns

**Cons:**
- Complex cross-region orchestration
- Duplicate infrastructure costs
- Cross-region data transfer costs
- Increased operational complexity

**Architecture:**
```
EU-CENTRAL-1: API, Frontend, DynamoDB, EventBridge
      │
      ├─── Cross-region EventBridge rule
      │
      ▼
US-EAST-1: ECS Workers + Nova Act Service
```

---

### Option 3: Hybrid Approach (Best for Scale)

**Description:** Keep wizard mode in eu-central-1 with SDK calls, deploy batch/scheduled workflows to us-east-1.

**Pros:**
- Optimizes for different use cases
- Interactive wizard stays low-latency
- Batch jobs benefit from us-east-1 proximity
- Gradual migration path

**Cons:**
- Two deployment patterns to maintain
- More complex architecture

---

## Recommended Approach: Option 1 (SDK-Based)

### Rationale
1. **Minimal Changes:** Leverages existing architecture
2. **Cost-Effective:** No duplicate infrastructure
3. **Latency Acceptable:** 80-120ms cross-region latency is acceptable for automation workflows
4. **Proven Pattern:** SDK handles cross-region complexity

---

## Implementation Specifications

### 1. Worker Code Changes

#### File: `worker/wizard_worker.py`

**Current (Preview API):**
```python
with NovaAct(
    cdp_endpoint_url=ws_url,
    cdp_headers=headers,
    starting_page=execution.starting_url,
    headless=execution.headless,
    logs_directory=execution_logs_dir,
    ignore_https_errors=True,
    chrome_channel="chromium",
    stop_hooks=[s3_writer],
    nova_act_api_key=nova_api_key,  # Preview API key
    user_agent=os.getenv('USER_AGENT', 'Mozilla/5.0')
) as nova:
```

**Target (GA Service):**
```python
from nova_act import NovaAct, Workflow

# Create workflow context
with Workflow(
    workflow_definition_name=f"qa-studio-{usecase_id}",
    model_id="nova-act-latest",
    region="us-east-1"
) as workflow:
    with NovaAct(
        cdp_endpoint_url=ws_url,
        cdp_headers=headers,
        starting_page=execution.starting_url,
        workflow=workflow,
        headless=execution.headless,
        logs_directory=execution_logs_dir,
        ignore_https_errors=True,
        chrome_channel="chromium",
        stop_hooks=[s3_writer],
        user_agent=os.getenv('USER_AGENT', 'Mozilla/5.0')
    ) as nova:
```

**Key Changes:**
- Remove `nova_act_api_key` parameter
- Add `Workflow` context manager with us-east-1 region
- Add `workflow` parameter to NovaAct
- SDK uses AWS IAM credentials automatically

---

### 2. IAM Policy Updates

#### File: `lib/worker-stack.ts`

**Add Nova Act Permissions:**
```typescript
// Add to task execution role
const novaActPolicy = new PolicyStatement({
  effect: Effect.ALLOW,
  actions: [
    'nova-act:CreateWorkflowDefinition',
    'nova-act:GetWorkflowDefinition',
    'nova-act:CreateWorkflowRun',
    'nova-act:CreateSession',
    'nova-act:CreateAct',
    'nova-act:InvokeActStep',
    'nova-act:UpdateAct',
    'nova-act:UpdateWorkflowRun',
    'nova-act:GetWorkflowRun',
    'nova-act:ListWorkflowRuns',
    'nova-act:ListSessions',
    'nova-act:ListActs',
  ],
  resources: ['*'],
  conditions: {
    StringEquals: {
      'aws:RequestedRegion': 'us-east-1'
    }
  }
});

taskDefinition.taskRole.addToPolicy(novaActPolicy);

// Add service-linked role creation permission
const slrPolicy = new PolicyStatement({
  effect: Effect.ALLOW,
  actions: ['iam:CreateServiceLinkedRole'],
  resources: [
    'arn:aws:iam::*:role/aws-service-role/nova-act.amazonaws.com/AWSServiceRoleForNovaAct'
  ],
  conditions: {
    StringLike: {
      'iam:AWSServiceName': 'nova-act.amazonaws.com'
    }
  }
});

taskDefinition.taskRole.addToPolicy(slrPolicy);
```

---

### 3. Workflow Definition Management

**S3 Bucket Requirement:**
Nova Act workflow definitions require an S3 bucket in us-east-1 for storing workflow artifacts and execution data.

**Good News:** Your architecture already has this! 
- Existing bucket: `<account>-nova-act-qa-studio-modular-artefacts-us-east-1`
- Already configured with cross-region replication to eu-central-1
- Created via `createCrossRegionBucket()` in worker-stack.ts

#### Option A: Pre-create Workflow Definitions (Recommended)

**Create via AWS CLI:**
```bash
# One-time setup - use existing us-east-1 bucket
aws nova-act create-workflow-definition \
  --name "qa-studio-wizard" \
  --description "QA Studio wizard mode workflow" \
  --s3-bucket-name "<account>-nova-act-qa-studio-modular-artefacts-us-east-1" \
  --region us-east-1
```

**Or via Nova Act CLI:**
```bash
# Configure Nova Act CLI with us-east-1 bucket
act workflow create \
  --name "qa-studio-wizard" \
  --region us-east-1 \
  --s3-bucket-name "<account>-nova-act-qa-studio-modular-artefacts-us-east-1"
```

**Store workflow definition name in DynamoDB:**
```typescript
// Add to usecase table schema
{
  pk: "USECASE#<usecase_id>",
  sk: "METADATA",
  workflow_definition_name: "qa-studio-wizard",
  // ... other fields
}
```

#### Option B: Dynamic Workflow Definition Creation

**Create on-demand in worker:**
```python
import boto3
import os

def ensure_workflow_definition(usecase_id: str) -> str:
    """Ensure workflow definition exists, create if needed"""
    client = boto3.client('nova-act', region_name='us-east-1')
    workflow_name = f"qa-studio-{usecase_id}"
    s3_bucket = os.getenv('NOVA_ACT_S3_BUCKET_US_EAST_1')
    
    try:
        client.get_workflow_definition(name=workflow_name)
        logger.info(f"Workflow definition {workflow_name} exists")
    except client.exceptions.ResourceNotFoundException:
        logger.info(f"Creating workflow definition {workflow_name}")
        client.create_workflow_definition(
            name=workflow_name,
            description=f"QA Studio workflow for usecase {usecase_id}",
            s3BucketName=s3_bucket
        )
    
    return workflow_name
```

---

### 4. Environment Variables

**Add to ECS Task Definition:**
```typescript
// In lib/worker-stack.ts, update container environment
container.addEnvironment('NOVA_ACT_REGION', 'us-east-1');
container.addEnvironment('AWS_REGION_NOVA_ACT', 'us-east-1');
container.addEnvironment(
  'NOVA_ACT_S3_BUCKET_US_EAST_1', 
  `${this.account}-${this.baseName}-artefacts-us-east-1`
);
```

**Remove from Task Definition:**
```typescript
// Remove API key secret
// container.addSecret('NOVA_ACT_API_KEY', ...)
```

**Note:** The us-east-1 S3 bucket already exists in your architecture:
- Created by `createCrossRegionBucket('us-east-1')` in worker-stack.ts
- Configured with cross-region replication to eu-central-1
- Used for storing Nova Act workflow artifacts and execution data

---

### 5. Monitoring & Observability

#### CloudWatch Metrics (us-east-1)

**Create cross-region dashboard:**
```typescript
import { Dashboard, GraphWidget, Metric } from 'aws-cdk-lib/aws-cloudwatch';

const novaActDashboard = new Dashboard(this, 'NovaActMetrics', {
  dashboardName: `${baseName}-nova-act-metrics`,
});

novaActDashboard.addWidgets(
  new GraphWidget({
    title: 'Nova Act Invocations',
    left: [
      new Metric({
        namespace: 'AWS/NovaAct',
        metricName: 'Invocations',
        dimensionsMap: {
          Workflow: 'qa-studio-wizard',
        },
        region: 'us-east-1',
        statistic: 'Sum',
      }),
    ],
  }),
  new GraphWidget({
    title: 'Nova Act Latency',
    left: [
      new Metric({
        namespace: 'AWS/NovaAct',
        metricName: 'Latency',
        dimensionsMap: {
          Workflow: 'qa-studio-wizard',
        },
        region: 'us-east-1',
        statistic: 'Average',
      }),
    ],
  }),
  new GraphWidget({
    title: 'Nova Act Errors',
    left: [
      new Metric({
        namespace: 'AWS/NovaAct',
        metricName: 'UserErrors',
        dimensionsMap: {
          Workflow: 'qa-studio-wizard',
        },
        region: 'us-east-1',
        statistic: 'Sum',
      }),
      new Metric({
        namespace: 'AWS/NovaAct',
        metricName: 'SystemErrors',
        dimensionsMap: {
          Workflow: 'qa-studio-wizard',
        },
        region: 'us-east-1',
        statistic: 'Sum',
      }),
    ],
  }),
);
```

#### Custom Metrics

**Track cross-region latency:**
```python
import time
from aws_embedded_metrics import metric_scope

@metric_scope
def track_nova_act_call(metrics, operation: str):
    start = time.time()
    try:
        # Nova Act operation
        yield
        duration = (time.time() - start) * 1000
        metrics.put_metric("NovaActCrossRegionLatency", duration, "Milliseconds")
        metrics.set_property("Operation", operation)
        metrics.set_property("SourceRegion", "eu-central-1")
        metrics.set_property("TargetRegion", "us-east-1")
    except Exception as e:
        metrics.put_metric("NovaActCrossRegionError", 1, "Count")
        raise
```

---

### 6. Error Handling & Retry Logic

**Add cross-region resilience:**
```python
from botocore.config import Config
from botocore.exceptions import ClientError
import time

# Configure SDK with retry logic
nova_act_config = Config(
    region_name='us-east-1',
    retries={
        'max_attempts': 3,
        'mode': 'adaptive'
    },
    connect_timeout=10,
    read_timeout=60
)

def execute_with_retry(func, max_retries=3, backoff=2):
    """Execute function with exponential backoff"""
    for attempt in range(max_retries):
        try:
            return func()
        except ClientError as e:
            error_code = e.response['Error']['Code']
            
            # Don't retry user errors
            if error_code in ['ValidationException', 'InvalidParameterException']:
                raise
            
            # Retry throttling and service errors
            if attempt < max_retries - 1:
                wait_time = backoff ** attempt
                logger.warning(f"Retry {attempt + 1}/{max_retries} after {wait_time}s: {error_code}")
                time.sleep(wait_time)
            else:
                raise
```

---

### 7. Cost Optimization

#### Data Transfer Costs

**Estimated costs:**
- Cross-region data transfer (EU→US): $0.02/GB
- Typical workflow: ~5MB per execution (screenshots, logs)
- 1000 executions/day = 5GB/day = $0.10/day = $3/month

**Optimization strategies:**
1. **Compress screenshots before transfer**
2. **Store artifacts in eu-central-1 S3** (already doing this)
3. **Only send minimal data to Nova Act** (instructions, not full context)

#### Nova Act Service Costs

**Pricing (from documentation):**
- Visit pricing page: https://aws.amazon.com/nova/pricing/
- Charged per step execution
- Monitor via CloudWatch metrics

---

### 8. Security Considerations

#### Cross-Region IAM

**Ensure IAM policies allow cross-region:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "nova-act:*",
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestedRegion": "us-east-1"
        }
      }
    }
  ]
}
```

#### Data Residency

**Important:** Nova Act processes data in us-east-1:
- Screenshots sent to us-east-1
- Workflow execution data stored in us-east-1
- Ensure compliance with data residency requirements
- Consider data classification before migration

**Mitigation:**
- Store sensitive artifacts only in eu-central-1 S3
- Redact PII before sending to Nova Act
- Use SDK security options (state guardrails, domain restrictions)

---

### 9. Migration Strategy

#### Phase 1: Preparation (Week 1)
- [ ] Update IAM policies in CDK
- [ ] Add Nova Act permissions to worker role
- [ ] Create workflow definitions in us-east-1
- [ ] Update worker Docker image with new SDK code
- [ ] Deploy to dev environment

#### Phase 2: Testing (Week 2)
- [ ] Test single workflow execution
- [ ] Validate cross-region latency
- [ ] Test error handling and retries
- [ ] Verify CloudWatch metrics
- [ ] Load test with 10 concurrent executions

#### Phase 3: Staged Rollout (Week 3)
- [ ] Deploy to staging environment
- [ ] Run parallel testing (Preview API vs GA)
- [ ] Monitor for 48 hours
- [ ] Compare success rates and latency

#### Phase 4: Production Migration (Week 4)
- [ ] Deploy to production
- [ ] Monitor closely for 24 hours
- [ ] Keep Preview API as fallback
- [ ] Full cutover after validation

#### Phase 5: Cleanup (Week 5)
- [ ] Remove Preview API key from Secrets Manager
- [ ] Remove old code paths
- [ ] Update documentation
- [ ] Archive Preview API artifacts

---

### 10. Rollback Plan

**If issues occur:**

1. **Immediate rollback:**
   ```bash
   # Revert to previous task definition
   aws ecs update-service \
     --cluster qa-studio-cluster \
     --service wizard-worker \
     --task-definition qa-studio-worker:PREVIOUS_VERSION \
     --region eu-central-1
   ```

2. **Code-level fallback:**
   ```python
   USE_GA_SERVICE = os.getenv('USE_NOVA_ACT_GA', 'false').lower() == 'true'
   
   if USE_GA_SERVICE:
       # GA service code path
       with Workflow(...) as workflow:
           with NovaAct(workflow=workflow, ...) as nova:
               ...
   else:
       # Preview API code path (fallback)
       with NovaAct(nova_act_api_key=api_key, ...) as nova:
           ...
   ```

---

## Performance Expectations

### Latency Impact

| Operation | Preview API | GA Service (Cross-Region) | Delta |
|-----------|-------------|---------------------------|-------|
| Session Init | 500ms | 600-650ms | +100-150ms |
| Act Call | 2-5s | 2.1-5.1s | +100ms |
| Step Execution | 3-8s | 3.1-8.1s | +100ms |

**Conclusion:** Cross-region latency adds ~100ms per operation, negligible for automation workflows.

---

## Resource Requirements

### Additional AWS Resources

1. **IAM Policies:** +2 policy statements
2. **CloudWatch Dashboards:** +1 cross-region dashboard (optional)
3. **Workflow Definitions:** 1 per usecase (lightweight, stored in S3)
4. **S3 Bucket Permissions:** Grant Nova Act service access to us-east-1 bucket

**Note:** No new S3 buckets required! Your existing us-east-1 bucket is already configured:
- Bucket name: `<account>-nova-act-qa-studio-modular-artefacts-us-east-1`
- Already has cross-region replication from eu-central-1
- Will be used by Nova Act for workflow definitions and execution traces

### No Additional Infrastructure

- No new VPCs, subnets, or networking
- No new compute resources
- No new databases

---

## Testing Checklist

- [ ] Worker can authenticate to us-east-1 Nova Act service
- [ ] Workflow definitions created successfully
- [ ] Single step execution works
- [ ] Multi-step workflow completes
- [ ] Error handling works (network failures, throttling)
- [ ] Retry logic functions correctly
- [ ] CloudWatch metrics appear in us-east-1
- [ ] Cross-region latency acceptable (<200ms overhead)
- [ ] Artifacts still stored in eu-central-1 S3
- [ ] Live view still works with DCV
- [ ] Wizard mode commands work end-to-end
- [ ] Concurrent executions don't interfere
- [ ] Service quotas sufficient (100 TPS default)

---

## Open Questions

1. **Workflow Definition Naming:**
   - One workflow per usecase? Or shared workflow?
   - Recommendation: Shared workflow "qa-studio-wizard" for all usecases

2. **Model Selection:**
   - Use `nova-act-latest` (auto-updates) or pin to `nova-act-v1.0`?
   - Recommendation: Start with `nova-act-latest`, pin if stability issues

3. **Observability:**
   - Store Nova Act session IDs in DynamoDB for correlation?
   - Recommendation: Yes, add `nova_act_session_id` field

4. **Data Residency:**
   - Any compliance concerns with data in us-east-1?
   - Action: Verify with compliance team

---

## Next Steps

1. **Review this specification** with team
2. **Validate data residency** requirements
3. **Create implementation tickets** based on migration phases
4. **Set up dev environment** for testing
5. **Begin Phase 1 implementation**

---

## References

- Nova Act User Guide: https://docs.aws.amazon.com/nova-act/latest/userguide/
- Nova Act SDK: https://github.com/awslabs/nova-act
- AWS Regions: https://aws.amazon.com/about-aws/global-infrastructure/regions_az/
- Cross-Region Latency: ~80-120ms EU→US (typical)
