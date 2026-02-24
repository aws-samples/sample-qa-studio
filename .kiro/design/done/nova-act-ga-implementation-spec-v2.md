# Nova Act GA Migration - Implementation Specification v2

**Project:** nova-act-qa-studio  
**Objective:** Migrate from Nova Act Preview API to GA Service  
**Approach:** Configuration-based feature flag with sane defaults

---

## Overview

Add Nova Act GA service support using the existing configuration system. The feature will be disabled by default (`useNovaActGa: false`) and can be enabled via `configuration.json`.

---

## Implementation Steps

### Step 1: Update Configuration Interface

**File:** `lib/config.ts`

**Action:** Add `useNovaActGa` to interface and defaults

```typescript
export interface NovaActQAStudioConfig {
  adminEmail: string;
  baseName: string;
  apiEndpoint: string;
  apiDeploymentStage: string;
  enabledRegions: string[];
  defaultRegion: string;
  userAgentString: string;
  bedrockModelId: string;
  dcvRelease: string;
  vpcId: string | null;
  workerSecurityGroupId: string | null;
  createVpcEndpoints: boolean;
  useNovaActGa: boolean;  // ADD THIS
}

const DEFAULT_CONFIG: Partial<NovaActQAStudioConfig> = {
  apiEndpoint: 'api',
  apiDeploymentStage: 'api',
  enabledRegions: ['us-east-1'],
  defaultRegion: 'us-east-1',
  userAgentString: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
  bedrockModelId: 'anthropic.claude-3-5-sonnet-20240620-v1:0',
  dcvRelease: 'https://d1uj6qtbmh3dt5.cloudfront.net/webclientsdk/nice-dcv-web-client-sdk-1.9.100-952.zip',
  vpcId: null,
  workerSecurityGroupId: null,
  createVpcEndpoints: false,
  useNovaActGa: false,  // ADD THIS - Default to Preview API
};
```

---

### Step 2: Update Worker Stack

**File:** `lib/worker-stack.ts`

#### 2.1 Import config at top of file

```typescript
import { loadConfig } from './config';

const config = loadConfig();
```

#### 2.2 Add environment variable (line ~229)

```typescript
environment: {
  DYNAMO_TABLE: props.table.tableName,
  QUEUE_URL: this.executionQueue.queueUrl,
  S3_BUCKET: this.artefactsBucket.bucketName,
  NOVA_ACT_API_KEY_NAME: props.novaActApiKeySecret.secretName,
  NOTIFICATION_QUEUE_URL: props.notificationQueue.queueUrl,
  AWS_REGION: Aws.REGION,
  // Nova Act GA Service configuration
  USE_NOVA_ACT_GA: config.useNovaActGa.toString(),
  NOVA_ACT_REGION: 'us-east-1',
  NOVA_ACT_S3_BUCKET: `${this.account}-${this.baseName}-artefacts-us-east-1`,
}
```

#### 2.3 Add IAM permissions (after line ~237)

```typescript
// Grant permissions to task roles
this.executionQueue.grantConsumeMessages(this.taskDefinition.taskRole);
wizardQueue.grantConsumeMessages(this.taskDefinition.taskRole);
props.table.grantFullAccess(this.taskDefinition.taskRole);
this.artefactsBucket.grantReadWrite(this.taskDefinition.taskRole);
props.notificationQueue.grantSendMessages(this.taskDefinition.taskRole);

// ADD THIS BLOCK:
// Nova Act GA Service permissions (only if enabled)
if (config.useNovaActGa) {
  this.taskDefinition.taskRole.addToPolicy(new PolicyStatement({
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
  }));

  // Service-linked role creation permission
  this.taskDefinition.taskRole.addToPolicy(new PolicyStatement({
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
  }));

  // S3 permissions for us-east-1 bucket
  const usEast1BucketArn = `arn:aws:s3:::${this.account}-${this.baseName}-artefacts-us-east-1`;
  this.taskDefinition.taskRole.addToPolicy(new PolicyStatement({
    effect: Effect.ALLOW,
    actions: [
      's3:GetObject',
      's3:PutObject',
      's3:ListBucket',
      's3:DeleteObject'
    ],
    resources: [
      usEast1BucketArn,
      `${usEast1BucketArn}/*`
    ]
  }));
}
```

---

### Step 3: Update Worker Code

**File:** `worker/wizard_worker.py`

#### 3.1 Add imports and constants (top of file)

```python
from nova_act import NovaAct, Workflow
from botocore.config import Config

INACTIVITY_TIMEOUT = 30 * 60
NOVA_ACT_REGION = 'us-east-1'
```

#### 3.2 Add workflow definition helper (after imports)

```python
def ensure_workflow_definition(usecase_id: str) -> str:
    """Ensure workflow definition exists in us-east-1"""
    workflow_name = "qa-studio-wizard"
    s3_bucket = os.getenv('NOVA_ACT_S3_BUCKET')
    
    if not s3_bucket:
        logger.warning("NOVA_ACT_S3_BUCKET not set, using shared workflow")
        return workflow_name
    
    try:
        client = boto3.client('bedrock-agent', region_name=NOVA_ACT_REGION)
        client.get_flow(flowIdentifier=workflow_name)
        logger.info(f"Workflow definition {workflow_name} exists")
    except client.exceptions.ResourceNotFoundException:
        logger.info(f"Workflow definition {workflow_name} will be created by SDK")
    except Exception as e:
        logger.warning(f"Could not check workflow: {e}")
    
    return workflow_name
```

#### 3.3 Update NovaAct initialization (line ~240)

**Replace:**
```python
# Initialize NovaAct
with NovaAct(
    cdp_endpoint_url=ws_url,
    cdp_headers=headers,
    starting_page=execution.starting_url,
    headless=execution.headless,
    logs_directory=execution_logs_dir,
    ignore_https_errors=True,
    chrome_channel="chromium",
    stop_hooks=[s3_writer],
    nova_act_api_key=nova_api_key,
    user_agent=os.getenv('USER_AGENT', 'Mozilla/5.0')
) as nova:
```

**With:**
```python
# Check if using GA service
use_ga_service = os.getenv('USE_NOVA_ACT_GA', 'false').lower() == 'true'

if use_ga_service:
    # Nova Act GA Service
    logger.info(f"Using Nova Act GA service in {NOVA_ACT_REGION}")
    workflow_name = ensure_workflow_definition(usecase_id)
    
    with Workflow(
        workflow_definition_name=workflow_name,
        model_id="nova-act-latest",
        region=NOVA_ACT_REGION
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
            # Existing code continues...
else:
    # Nova Act Preview API
    logger.info("Using Nova Act Preview API")
    
    with NovaAct(
        cdp_endpoint_url=ws_url,
        cdp_headers=headers,
        starting_page=execution.starting_url,
        headless=execution.headless,
        logs_directory=execution_logs_dir,
        ignore_https_errors=True,
        chrome_channel="chromium",
        stop_hooks=[s3_writer],
        nova_act_api_key=nova_api_key,
        user_agent=os.getenv('USER_AGENT', 'Mozilla/5.0')
    ) as nova:
        # Existing code continues...
```

#### 3.4 Update restart logic (line ~390)

Add same conditional logic for restart command to reinitialize with correct mode.

---

### Step 4: Update README

**File:** `README.md`

**Add after "Prerequisites" section:**

```markdown
## Configuration

Nova Act QA Studio uses a `configuration.json` file for deployment settings. Create this file in the project root:

```json
{
  "adminEmail": "your-email@example.com",
  "baseName": "nova-act-qa-studio",
  "enabledRegions": ["us-east-1", "eu-central-1"],
  "defaultRegion": "eu-central-1"
}
```

### Configuration Options

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `adminEmail` | string | Yes | - | Admin email for Cognito user pool |
| `baseName` | string | Yes | - | Base name for AWS resources (lowercase, alphanumeric, hyphens) |
| `apiEndpoint` | string | No | `"api"` | API Gateway endpoint name |
| `apiDeploymentStage` | string | No | `"api"` | API Gateway deployment stage |
| `enabledRegions` | string[] | No | `["us-east-1"]` | AWS regions for worker deployment |
| `defaultRegion` | string | No | `"us-east-1"` | Primary region for deployment |
| `userAgentString` | string | No | Chrome UA | User agent for browser automation |
| `bedrockModelId` | string | No | Claude 3.5 Sonnet | Bedrock model for AI features |
| `vpcId` | string | No | `null` | Existing VPC ID (creates new if null) |
| `workerSecurityGroupId` | string | No | `null` | Existing security group ID |
| `createVpcEndpoints` | boolean | No | `false` | Create VPC endpoints for AWS services |
| `useNovaActGa` | boolean | No | `false` | Use Nova Act GA service (us-east-1 only) |

### Nova Act GA Service

Nova Act QA Studio supports both the Preview API and the GA service:

- **Preview API** (default): Free tier, region-agnostic, API key authentication
- **GA Service**: Production service, us-east-1 only, AWS IAM authentication, pay-per-use

To enable the GA service, add to `configuration.json`:

```json
{
  "useNovaActGa": true,
  "enabledRegions": ["us-east-1", "eu-central-1"]
}
```

**Requirements for GA service:**
- `us-east-1` must be in `enabledRegions` (for S3 bucket)
- IAM permissions for `nova-act:*` actions
- S3 bucket in us-east-1 for workflow definitions

**Note:** When enabled, worker makes cross-region calls from your `defaultRegion` to us-east-1. Expect ~100ms additional latency per operation.
```

---

## Deployment

### Initial Deployment (GA Disabled)

```bash
# 1. Create configuration.json
cat > configuration.json << EOF
{
  "adminEmail": "your-email@example.com",
  "baseName": "nova-act-qa-studio",
  "enabledRegions": ["us-east-1", "eu-central-1"],
  "defaultRegion": "eu-central-1",
  "useNovaActGa": false
}
EOF

# 2. Deploy
cdk deploy --all
```

### Enable GA Service

```bash
# 1. Update configuration.json
# Change "useNovaActGa": false to "useNovaActGa": true

# 2. Redeploy worker stack
cdk deploy NovaActQAStudioWorkerStack
```

### Verify

```bash
# Check environment variable
aws ecs describe-task-definition \
  --task-definition <task-def-name> \
  --region eu-central-1 \
  --query 'taskDefinition.containerDefinitions[0].environment' \
  | grep USE_NOVA_ACT_GA

# Check logs
aws logs tail /aws/ecs/<log-group> --follow --region eu-central-1
```

**Expected log when enabled:** `"Using Nova Act GA service in us-east-1"`  
**Expected log when disabled:** `"Using Nova Act Preview API"`

---

## Rollback

Edit `configuration.json`:

```json
{
  "useNovaActGa": false
}
```

Redeploy:

```bash
cdk deploy NovaActQAStudioWorkerStack
```

---

## Testing Checklist

- [ ] Config loads with `useNovaActGa: false` by default
- [ ] Can override in `configuration.json`
- [ ] CDK synthesizes without errors
- [ ] Worker deploys successfully
- [ ] Preview API works (flag=false)
- [ ] GA service works (flag=true)
- [ ] IAM permissions only added when enabled
- [ ] Environment variable reflects config value
- [ ] README documents configuration option
- [ ] Rollback works

---

## Files Modified

1. `lib/config.ts` - Add `useNovaActGa` to interface and defaults
2. `lib/worker-stack.ts` - Add environment variable and conditional IAM policies
3. `worker/wizard_worker.py` - Add feature flag check and dual code paths
4. `README.md` - Document configuration option
5. `configuration.json` - User can optionally add `"useNovaActGa": true`

---

## Summary

- ✅ Configuration-based approach (not hardcoded)
- ✅ Sane default (`false` - Preview API)
- ✅ Easy to enable via `configuration.json`
- ✅ IAM permissions only added when needed
- ✅ No monitoring dashboard (removed from spec)
- ✅ Clean rollback path
- ✅ Documented in README
