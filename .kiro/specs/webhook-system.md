# Webhook System Specification

## Overview

Add bidirectional webhook system to Nova Act QA Studio:
- **Inbound**: External systems (CI/CD) trigger usecase executions via API keys
- **Outbound**: Studio notifies external systems when executions complete

Both inbound and outbound webhooks are **system-wide** - all users can create, view, and manage all webhooks.

## Use Cases

### Inbound
- GitHub Actions triggers test execution on PR
- Jenkins pipeline runs QA tests before deployment
- External monitoring system triggers health checks
- Scheduled jobs from external systems

### Outbound
- Notify CI/CD pipeline when tests complete
- Send results to Slack/Teams
- Update external dashboards
- Trigger downstream workflows

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              Nova Act QA Studio                      │
├─────────────────────────────────────────────────────┤
│                                                       │
│  INBOUND                        OUTBOUND             │
│  ┌──────────────┐              ┌──────────────┐     │
│  │ API Gateway  │              │  Dispatch    │     │
│  │ (API Keys)   │              │  Lambda      │     │
│  └──────┬───────┘              └──────▲───────┘     │
│         │                             │              │
│         v                             │              │
│  ┌──────────────┐              ┌──────────────┐     │
│  │  Execute     │─────────────▶│  Webhook     │     │
│  │  Usecase     │              │  Queue (SQS) │     │
│  │  Lambda      │              └──────────────┘     │
│  └──────────────┘                                    │
│         │                                            │
│         v                                            │
│  ┌──────────────────────────────────┐               │
│  │         DynamoDB                  │               │
│  │  PK: SYSTEM                       │               │
│  │  - Inbound API Keys               │               │
│  │  - Outbound Webhook Configs       │               │
│  └──────────────────────────────────┘               │
└─────────────────────────────────────────────────────┘
         ▲                                   │
         │ Trigger                           │ Notify
         │                                   v
┌────────────────────┐            ┌────────────────────┐
│   CI/CD Pipeline   │            │   CI/CD Pipeline   │
│   X-API-Key: xxx   │            │   Webhook Receiver │
└────────────────────┘            └────────────────────┘
```

## Data Model

### DynamoDB Schema

```
# Inbound API Keys (system-wide)
PK: SYSTEM
SK: INBOUND_KEY#<key_id>
key_id: string (API Gateway key ID)
name: string ("Production CI/CD")
created_by: string (user email)
created_at: timestamp
last_used: timestamp

# Outbound Webhooks (system-wide)
PK: SYSTEM
SK: OUTBOUND_WEBHOOK#<webhook_id>
webhook_id: uuid
name: string ("Notify Jenkins")
url: string (HTTPS only)
secret: string (for HMAC signing)
events: ["execution.completed", "execution.failed", "execution.started"]
usecase_filters: ["usecase-123"] (optional, empty = all)
enabled: boolean
created_by: string (user email)
created_at: timestamp
updated_at: timestamp
retry_config: {
  max_attempts: 3,
  backoff_seconds: [1, 2, 4]
}

# Webhook Delivery Log
PK: WEBHOOK#<webhook_id>
SK: DELIVERY#<timestamp>#<execution_id>
execution_id: string
status: "success" | "failed"
status_code: number
response_time_ms: number
error_message: string (if failed)
retry_count: number
delivered_at: timestamp
```

## API Endpoints

### Inbound Key Management (Cognito Auth)

#### Create Inbound API Key
```
POST /inbound-keys
Authorization: Bearer <cognito-jwt>

Request:
{
  "name": "Production CI/CD"
}

Response:
{
  "key_id": "abc123",
  "api_key": "xyz789...",  // Only shown once
  "name": "Production CI/CD",
  "created_by": "user@example.com",
  "created_at": "2025-12-04T10:00:00Z"
}
```

#### List Inbound API Keys
```
GET /inbound-keys
Authorization: Bearer <cognito-jwt>

Response:
{
  "keys": [
    {
      "key_id": "abc123",
      "name": "Production CI/CD",
      "created_by": "user@example.com",
      "created_at": "2025-12-04T10:00:00Z",
      "last_used": "2025-12-04T10:30:00Z"
    }
  ]
}
```

#### Delete Inbound API Key
```
DELETE /inbound-keys/{key_id}
Authorization: Bearer <cognito-jwt>

Response: 204 No Content
```

### Inbound Execution (API Key Auth)

#### Trigger Usecase Execution
```
POST /webhooks/inbound/execute
X-API-Key: <api-key>

Request:
{
  "usecase_id": "usecase-123",
  "variables": {
    "env": "production",
    "branch": "main"
  },
  "region": "us-east-1"  // optional
}

Response:
{
  "execution_id": "exec-456",
  "usecase_id": "usecase-123",
  "status": "queued",
  "queued_at": "2025-12-04T10:00:00Z"
}
```

#### Get Execution Status
```
GET /webhooks/inbound/status/{execution_id}
X-API-Key: <api-key>

Response:
{
  "execution_id": "exec-456",
  "usecase_id": "usecase-123",
  "status": "running",
  "started_at": "2025-12-04T10:00:00Z",
  "current_step": 3,
  "total_steps": 10
}
```

### Outbound Webhook Management (Cognito Auth)

#### Create Outbound Webhook
```
POST /outbound-webhooks
Authorization: Bearer <cognito-jwt>

Request:
{
  "name": "Notify Jenkins",
  "url": "https://jenkins.example.com/webhook",
  "events": ["execution.completed", "execution.failed"],
  "usecase_filters": ["usecase-123"],  // optional
  "enabled": true
}

Response:
{
  "webhook_id": "webhook-789",
  "name": "Notify Jenkins",
  "url": "https://jenkins.example.com/webhook",
  "secret": "whsec_abc123...",  // For HMAC verification
  "events": ["execution.completed", "execution.failed"],
  "usecase_filters": ["usecase-123"],
  "enabled": true,
  "created_by": "user@example.com",
  "created_at": "2025-12-04T10:00:00Z"
}
```

#### List Outbound Webhooks
```
GET /outbound-webhooks
Authorization: Bearer <cognito-jwt>

Response:
{
  "webhooks": [
    {
      "webhook_id": "webhook-789",
      "name": "Notify Jenkins",
      "url": "https://jenkins.example.com/webhook",
      "events": ["execution.completed"],
      "enabled": true,
      "created_by": "user@example.com",
      "created_at": "2025-12-04T10:00:00Z"
    }
  ]
}
```

#### Update Outbound Webhook
```
PUT /outbound-webhooks/{webhook_id}
Authorization: Bearer <cognito-jwt>

Request:
{
  "name": "Updated Name",
  "url": "https://new-url.com/webhook",
  "events": ["execution.completed"],
  "enabled": false
}

Response: Updated webhook object
```

#### Delete Outbound Webhook
```
DELETE /outbound-webhooks/{webhook_id}
Authorization: Bearer <cognito-jwt>

Response: 204 No Content
```

#### Test Outbound Webhook
```
POST /outbound-webhooks/{webhook_id}/test
Authorization: Bearer <cognito-jwt>

Response:
{
  "success": true,
  "status_code": 200,
  "response_time_ms": 145,
  "message": "Webhook delivered successfully"
}
```

## Webhook Payload Formats

### Outbound: Execution Started
```json
{
  "event": "execution.started",
  "timestamp": "2025-12-04T10:00:00Z",
  "webhook_id": "webhook-789",
  "data": {
    "execution_id": "exec-456",
    "usecase_id": "usecase-123",
    "usecase_name": "Login Test",
    "region": "us-east-1",
    "variables": {
      "env": "production"
    },
    "started_at": "2025-12-04T10:00:00Z"
  }
}
```

### Outbound: Execution Completed
```json
{
  "event": "execution.completed",
  "timestamp": "2025-12-04T10:02:00Z",
  "webhook_id": "webhook-789",
  "data": {
    "execution_id": "exec-456",
    "usecase_id": "usecase-123",
    "usecase_name": "Login Test",
    "status": "completed",
    "started_at": "2025-12-04T10:00:00Z",
    "completed_at": "2025-12-04T10:02:00Z",
    "duration_seconds": 120,
    "steps_total": 10,
    "steps_completed": 10,
    "steps_failed": 0,
    "artifacts": {
      "video_url": "https://s3.../video.mp4",
      "log_url": "https://s3.../log.txt"
    }
  }
}
```

### Outbound: Execution Failed
```json
{
  "event": "execution.failed",
  "timestamp": "2025-12-04T10:01:30Z",
  "webhook_id": "webhook-789",
  "data": {
    "execution_id": "exec-456",
    "usecase_id": "usecase-123",
    "usecase_name": "Login Test",
    "status": "failed",
    "started_at": "2025-12-04T10:00:00Z",
    "failed_at": "2025-12-04T10:01:30Z",
    "duration_seconds": 90,
    "steps_total": 10,
    "steps_completed": 5,
    "steps_failed": 1,
    "error": {
      "step_number": 6,
      "message": "Element not found"
    },
    "artifacts": {
      "video_url": "https://s3.../video.mp4",
      "log_url": "https://s3.../log.txt",
      "screenshot_url": "https://s3.../error.png"
    }
  }
}
```

### Outbound Security Headers
```
X-Webhook-Signature: sha256=<hmac-signature>
X-Webhook-ID: webhook-789
X-Webhook-Timestamp: 1733310000
Content-Type: application/json
User-Agent: NovaActQAStudio/1.0
```

## Implementation Plan

### Phase 1: Infrastructure

**1. Create Webhook Stack**
```
lib/webhook-stack.ts
- Webhook SQS queue
- Lambda functions (create/list/update/delete/test/dispatch)
- API Gateway usage plan for inbound keys
```

**2. Lambda Functions**
```
lambda/cmd/
  create_inbound_key/      - Creates API Gateway key
  list_inbound_keys/       - Lists all keys
  delete_inbound_key/      - Deletes key from API Gateway
  inbound_execute/         - Triggers usecase execution
  inbound_status/          - Returns execution status
  create_outbound_webhook/ - Creates webhook config
  list_outbound_webhooks/  - Lists all webhooks
  update_outbound_webhook/ - Updates webhook config
  delete_outbound_webhook/ - Deletes webhook config
  test_outbound_webhook/   - Sends test payload
  dispatch_webhook/        - Delivers webhook payloads
```

**3. Update Route Stack**
```typescript
// Inbound routes (API Key required)
const inboundResource = api.root.addResource('webhooks')
  .addResource('inbound');

inboundResource.addResource('execute')
  .addMethod('POST', integration, { apiKeyRequired: true });

inboundResource.addResource('status')
  .addResource('{execution_id}')
  .addMethod('GET', integration, { apiKeyRequired: true });

// Inbound key management (Cognito auth)
const inboundKeysResource = api.root.addResource('inbound-keys');
inboundKeysResource.addMethod('GET', listKeysIntegration, cognitoAuth);
inboundKeysResource.addMethod('POST', createKeyIntegration, cognitoAuth);
inboundKeysResource.addResource('{key_id}')
  .addMethod('DELETE', deleteKeyIntegration, cognitoAuth);

// Outbound webhook management (Cognito auth)
const outboundResource = api.root.addResource('outbound-webhooks');
outboundResource.addMethod('GET', listWebhooksIntegration, cognitoAuth);
outboundResource.addMethod('POST', createWebhookIntegration, cognitoAuth);

const webhookResource = outboundResource.addResource('{webhook_id}');
webhookResource.addMethod('PUT', updateWebhookIntegration, cognitoAuth);
webhookResource.addMethod('DELETE', deleteWebhookIntegration, cognitoAuth);
webhookResource.addResource('test')
  .addMethod('POST', testWebhookIntegration, cognitoAuth);
```

### Phase 2: Inbound Implementation

**create_inbound_key Lambda:**
```go
func handler(ctx context.Context, request events.APIGatewayProxyRequest) {
    userEmail := extractEmail(request)
    
    var input struct {
        Name string `json:"name"`
    }
    json.Unmarshal([]byte(request.Body), &input)
    
    // Create API Gateway key
    apiKey := apiGateway.CreateApiKey({
        Name: input.Name,
        Enabled: true
    })
    
    // Store metadata in DynamoDB
    dynamodb.PutItem({
        TableName: tableName,
        Item: {
            "PK": "SYSTEM",
            "SK": "INBOUND_KEY#" + apiKey.Id,
            "key_id": apiKey.Id,
            "name": input.Name,
            "created_by": userEmail,
            "created_at": time.Now()
        }
    })
    
    // Associate with usage plan
    apiGateway.CreateUsagePlanKey({
        UsagePlanId: usagePlanId,
        KeyId: apiKey.Id,
        KeyType: "API_KEY"
    })
    
    return response(200, {
        "key_id": apiKey.Id,
        "api_key": apiKey.Value,  // Only returned once
        "name": input.Name
    })
}
```

**inbound_execute Lambda:**
```go
func handler(ctx context.Context, request events.APIGatewayProxyRequest) {
    var input struct {
        UsecaseId string            `json:"usecase_id"`
        Variables map[string]string `json:"variables"`
        Region    string            `json:"region"`
    }
    json.Unmarshal([]byte(request.Body), &input)
    
    // Update last_used for API key
    apiKeyId := request.RequestContext.Identity.APIKeyID
    updateLastUsed(apiKeyId)
    
    // Queue execution (reuse existing execute_usecase logic)
    executionId := uuid.New().String()
    
    sqs.SendMessage({
        QueueUrl: executionQueueUrl,
        MessageBody: json.Marshal({
            "execution_id": executionId,
            "usecase_id": input.UsecaseId,
            "variables": input.Variables,
            "region": input.Region,
            "triggered_by": "webhook"
        })
    })
    
    return response(200, {
        "execution_id": executionId,
        "status": "queued"
    })
}
```

### Phase 3: Outbound Implementation

**dispatch_webhook Lambda:**
```go
func handler(ctx context.Context, sqsEvent events.SQSEvent) {
    for _, record := range sqsEvent.Records {
        var event struct {
            Event       string `json:"event"`
            ExecutionId string `json:"execution_id"`
            UsecaseId   string `json:"usecase_id"`
            Data        map[string]interface{} `json:"data"`
        }
        json.Unmarshal([]byte(record.Body), &event)
        
        // Query all enabled webhooks
        webhooks := queryWebhooks(event.Event, event.UsecaseId)
        
        for _, webhook := range webhooks {
            deliverWebhook(webhook, event)
        }
    }
}

func deliverWebhook(webhook Webhook, event Event) {
    payload := map[string]interface{}{
        "event": event.Event,
        "timestamp": time.Now().Format(time.RFC3339),
        "webhook_id": webhook.WebhookId,
        "data": event.Data,
    }
    
    payloadBytes, _ := json.Marshal(payload)
    
    // Generate HMAC signature
    signature := generateHMAC(payloadBytes, webhook.Secret)
    
    // Send HTTP request
    client := &http.Client{Timeout: 10 * time.Second}
    req, _ := http.NewRequest("POST", webhook.Url, bytes.NewBuffer(payloadBytes))
    req.Header.Set("Content-Type", "application/json")
    req.Header.Set("X-Webhook-Signature", "sha256=" + signature)
    req.Header.Set("X-Webhook-ID", webhook.WebhookId)
    req.Header.Set("X-Webhook-Timestamp", strconv.FormatInt(time.Now().Unix(), 10))
    
    start := time.Now()
    resp, err := client.Do(req)
    duration := time.Since(start).Milliseconds()
    
    // Log delivery
    logDelivery(webhook.WebhookId, event.ExecutionId, resp, err, duration)
    
    // Retry on failure
    if err != nil || resp.StatusCode >= 500 {
        retryWebhook(webhook, event, 1)
    }
}

func generateHMAC(payload []byte, secret string) string {
    mac := hmac.New(sha256.New, []byte(secret))
    mac.Write(payload)
    return hex.EncodeToString(mac.Sum(nil))
}
```

**Integration with existing execution flow:**
```go
// In existing execution completion handler
func onExecutionComplete(execution Execution) {
    // Existing notification logic...
    
    // Send to webhook queue
    sqs.SendMessage({
        QueueUrl: webhookQueueUrl,
        MessageBody: json.Marshal({
            "event": "execution.completed",
            "execution_id": execution.Id,
            "usecase_id": execution.UsecaseId,
            "data": {
                "execution_id": execution.Id,
                "usecase_id": execution.UsecaseId,
                "status": execution.Status,
                "started_at": execution.StartedAt,
                "completed_at": execution.CompletedAt,
                // ... full execution data
            }
        })
    })
}
```

### Phase 4: Frontend UI

**New Pages:**
```
src/pages/Webhooks/
  InboundKeys.tsx       - List/create/delete API keys
  OutboundWebhooks.tsx  - List/create/edit/delete webhooks
  WebhookForm.tsx       - Create/edit webhook form
  WebhookTest.tsx       - Test webhook delivery
```

**Navigation:**
- Add "Webhooks" menu item
- Two tabs: "Inbound Keys" and "Outbound Webhooks"

**Features:**
- Display API key once on creation (copy to clipboard)
- Show last used timestamp for keys
- Enable/disable toggle for webhooks
- Test button with real-time feedback
- Delivery logs viewer

### Phase 5: Security & Validation

**URL Validation:**
```go
func validateWebhookURL(url string) error {
    parsed, err := url.Parse(url)
    if err != nil {
        return errors.New("invalid URL")
    }
    if parsed.Scheme != "https" {
        return errors.New("only HTTPS URLs allowed")
    }
    // Optional: check DNS, IP blocklist
    return nil
}
```

**Rate Limiting:**
- API Gateway usage plan: 100 req/min per key
- Webhook delivery: Max 10 concurrent per webhook

**Signature Verification (for receivers):**
```python
# Example for webhook receivers
import hmac
import hashlib

def verify_webhook(payload, signature, secret):
    expected = hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
```

## Testing Strategy

### Unit Tests
- API key CRUD operations
- Webhook CRUD operations
- HMAC signature generation
- URL validation
- Event filtering logic

### Integration Tests
- End-to-end inbound execution
- End-to-end outbound delivery
- Retry mechanism
- API Gateway key validation

### Manual Testing
- Use webhook.site for testing outbound
- Test with real CI/CD systems
- Verify signature validation

## Deployment Steps

1. Deploy webhook stack: `npm run deploy:webhook`
2. Deploy route updates: `npm run deploy:routes`
3. Deploy frontend: `npm run deploy:frontend-build && npm run deploy:frontend-deployment`
4. Create initial usage plan in API Gateway
5. Test inbound/outbound flows

## Monitoring

### CloudWatch Metrics
- Inbound execution requests
- Outbound webhook delivery success rate
- Webhook delivery latency
- Failed delivery count
- Queue depth

### CloudWatch Alarms
- High failure rate (>10%)
- Queue depth >1000
- Delivery latency >5s

### DynamoDB Queries
- Recent deliveries per webhook
- Failed deliveries for retry
- API key usage statistics

## Documentation

### For Users
- How to create inbound API keys
- How to configure outbound webhooks
- Webhook payload examples
- Signature verification guide

### For Developers
- API endpoint documentation
- Integration examples (GitHub Actions, Jenkins)
- Troubleshooting guide
- Best practices

## Future Enhancements

- Webhook delivery dashboard with charts
- Custom retry policies per webhook
- Webhook templates (Slack, Discord, Teams)
- Batch webhook deliveries
- Webhook payload transformation
- IP allowlist for webhook sources
- Webhook delivery history pagination
