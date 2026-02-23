# Best Practices Guide

This guide provides recommendations for optimal usage of the Nova Act QA Studio CI/CD Runner, covering test suite organization, variable management, secret handling, artifact retention, performance optimization, and security best practices.

## Test Suite Organization

### Logical Grouping Strategies

Organize test suites by functional area, user journey, or testing purpose:

**By Functional Area**:
```
- Authentication Suite (login, logout, password reset)
- Checkout Suite (cart, payment, order confirmation)
- Search Suite (basic search, filters, sorting)
- Admin Suite (user management, settings, reports)
```

**By User Journey**:
```
- New User Onboarding Suite
- Power User Workflow Suite
- Guest Checkout Suite
- Mobile User Experience Suite
```

**By Testing Purpose**:
```
- Smoke Tests (critical paths, runs on every commit)
- Regression Tests (comprehensive coverage, runs nightly)
- Performance Tests (load testing, runs weekly)
- Security Tests (authentication, authorization, runs on release)
```

### Naming Conventions

Use clear, descriptive names that indicate purpose and scope:

**Good Examples**:
- `smoke-tests-critical-paths`
- `regression-checkout-flow`
- `security-authentication-tests`
- `performance-api-endpoints`

**Poor Examples**:
- `tests` (too generic)
- `suite1` (not descriptive)
- `my-tests` (unclear ownership)

### Suite Size Recommendations

Keep test suites focused and reasonably sized:

| Suite Type | Recommended Size | Execution Time | Run Frequency |
|------------|------------------|----------------|---------------|
| Smoke Tests | 5-15 use cases | 5-15 minutes | Every commit |
| Feature Tests | 10-30 use cases | 15-45 minutes | Every PR |
| Regression Tests | 30-100 use cases | 1-3 hours | Nightly |
| Full Suite | 100+ use cases | 3+ hours | Weekly |

**Benefits of Smaller Suites**:
- Faster feedback cycles
- Easier to identify failing tests
- Better parallelization opportunities
- Lower timeout risk
- Clearer purpose and ownership

**When to Split Suites**:
- Execution time exceeds 1 hour
- Suite contains unrelated test scenarios
- Different teams own different parts
- Different environments require different tests

### Suite Dependencies

Avoid dependencies between test suites:

**Good Practice**:
```
Each suite is independent and can run in any order:
- Suite A: Tests feature X
- Suite B: Tests feature Y
- Suite C: Tests feature Z
```

**Poor Practice**:
```
Suites depend on each other:
- Suite A: Creates test data
- Suite B: Uses data from Suite A (FRAGILE!)
- Suite C: Cleans up data from Suite A and B
```

**Recommendation**: Each suite should set up its own test data and clean up after itself.

## Variable Management

### Variable Naming Conventions

Use clear, consistent naming for variables:

**Recommended Patterns**:
- `snake_case` for multi-word variables: `api_key`, `base_url`, `user_email`
- Descriptive names: `admin_username` instead of `user1`
- Environment prefixes: `staging_api_key`, `prod_base_url`

**Examples**:
```bash
# Good
--var username=testuser
--var api_key=test_key_123
--var base_url=https://staging.example.com
--var admin_email=admin@example.com

# Poor
--var u=testuser
--var key=test_key_123
--var url=https://staging.example.com
--var e=admin@example.com
```

### Environment-Specific Variables

Organize variables by environment for clarity:

**CI/CD Configuration Example (GitHub Actions)**:
```yaml
env:
  # Staging environment
  STAGING_BASE_URL: https://staging.example.com
  STAGING_USERNAME: staging_user
  STAGING_API_KEY: ${{ secrets.STAGING_API_KEY }}
  
  # Production environment
  PROD_BASE_URL: https://production.example.com
  PROD_USERNAME: prod_user
  PROD_API_KEY: ${{ secrets.PROD_API_KEY }}

jobs:
  test-staging:
    runs-on: ubuntu-latest
    steps:
      - name: Run tests against staging
        run: |
          docker run --rm \
            -e OAUTH_CLIENT_ID="${{ secrets.OAUTH_CLIENT_ID }}" \
            -e OAUTH_CLIENT_SECRET="${{ secrets.OAUTH_CLIENT_SECRET }}" \
            -e OAUTH_TOKEN_ENDPOINT="${{ secrets.OAUTH_TOKEN_ENDPOINT }}" \
            -e API_ENDPOINT="${{ secrets.API_ENDPOINT }}" \
            nova-act-cicd-runner:latest \
            --suite-id ${{ vars.TEST_SUITE_ID }} \
            --base-url ${{ env.STAGING_BASE_URL }} \
            --var username=${{ env.STAGING_USERNAME }} \
            --var api_key=${{ env.STAGING_API_KEY }}
```

### Variable Precedence

Understand and leverage variable precedence (highest to lowest):

1. **CLI arguments** (`--var key=value`) - Highest priority
2. **Use case variables** (defined in test suite)
3. **Secrets** (from Secrets Manager) - Lowest priority

**Use Case**:
```bash
# Override production credentials for staging test
docker run --rm \
  -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID" \
  -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET" \
  -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT" \
  -e API_ENDPOINT="$API_ENDPOINT" \
  nova-act-cicd-runner:latest \
  --suite-id $SUITE_ID \
  --var username=staging_user \
  --var password=staging_pass \
  --var environment=staging
```

### Secret vs. Non-Secret Variables

Distinguish between sensitive and non-sensitive variables:

**Sensitive Variables** (use secrets management):
- Passwords
- API keys
- OAuth tokens
- Database credentials
- Encryption keys

**Non-Sensitive Variables** (can use plain variables):
- Usernames
- Email addresses
- Base URLs
- Environment names
- Feature flags

**Example**:
```yaml
# GitHub Actions
secrets:
  OAUTH_CLIENT_SECRET: ${{ secrets.OAUTH_CLIENT_SECRET }}
  API_KEY: ${{ secrets.API_KEY }}
  PASSWORD: ${{ secrets.PASSWORD }}

variables:
  USERNAME: testuser
  BASE_URL: https://staging.example.com
  ENVIRONMENT: staging
```

## Secret Handling

### Never Commit Secrets

**Critical Rule**: Never commit secrets to version control.

**Bad Practice**:
```bash
# DON'T DO THIS!
export OAUTH_CLIENT_SECRET="secret_xyz789..."
git add .env
git commit -m "Add configuration"
```

**Good Practice**:
```bash
# Add .env to .gitignore
echo ".env" >> .gitignore
echo ".token_cache.json" >> .gitignore

# Use environment variables or secrets management
export OAUTH_CLIENT_SECRET="$SECRET_FROM_VAULT"
```

### Use CI/CD Secret Management

Leverage your CI/CD platform's built-in secret management:

**GitHub Actions**:
```yaml
steps:
  - name: Run tests
    env:
      OAUTH_CLIENT_SECRET: ${{ secrets.OAUTH_CLIENT_SECRET }}
    run: |
      docker run --rm \
        -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET" \
        ...
```

**GitLab CI**:
```yaml
variables:
  OAUTH_CLIENT_SECRET: $OAUTH_CLIENT_SECRET  # Masked variable

test:
  script:
    - docker run --rm -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET" ...
```

**Jenkins**:
```groovy
environment {
  OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
}
```

### Secret Rotation Strategies

Rotate secrets regularly to minimize exposure risk:

**Recommended Rotation Schedule**:
- **OAuth client secrets**: Every 90 days
- **API keys**: Every 90 days
- **Passwords**: Every 90 days or after team member departure

**Rotation Process**:

1. **Create new OAuth client**:
```bash
curl -X POST \
  'https://api.example.com/api/oauth-clients' \
  -H 'Authorization: Bearer <jwt_token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "CI/CD Runner - Production (2024-Q2)",
    "scopes": [
      "api/suite.read",
      "api/suite.write",
      "api/execution.write"
    ]
  }'
```

2. **Update CI/CD secrets** with new credentials

3. **Test with new credentials** in non-production environment

4. **Deploy to production** pipelines

5. **Delete old OAuth client**:
```bash
curl -X DELETE \
  'https://api.example.com/api/oauth-clients/OLD_CLIENT_ID' \
  -H 'Authorization: Bearer <jwt_token>'
```

**Alternative: Use Rotate Secret Endpoint**:
```bash
# Rotate secret (changes client ID)
curl -X POST \
  'https://api.example.com/api/oauth-clients/CLIENT_ID/rotate-secret' \
  -H 'Authorization: Bearer <jwt_token>' \
  -H 'Content-Type: application/json'
```

**Note**: Rotation immediately invalidates old credentials. Update all systems before rotating.

### Least Privilege Principle

Grant only the minimum scopes required:

**Good Practice** (CI/CD runner needs execution only):
```json
{
  "name": "CI/CD Runner - Staging",
  "scopes": [
    "api/suite.read",
    "api/suite.write",
    "api/execution.write"
  ]
}
```

**Poor Practice** (unnecessary admin access):
```json
{
  "name": "CI/CD Runner - Staging",
  "scopes": [
    "api/admin"
  ]
}
```

**Scope Requirements by Use Case**:

| Use Case | Required Scopes |
|----------|----------------|
| Execute test suites | `api/suite.read`, `api/suite.write`, `api/execution.write` |
| Read-only monitoring | `api/suite.read`, `api/execution.read` |
| Manage OAuth clients | `api/oauth-clients.read`, `api/oauth-clients.write` |

### Secure Credential Storage

Store credentials securely in your CI/CD platform:

**GitHub Actions**:
- Use repository secrets (Settings → Secrets and variables → Actions)
- Mark secrets as "Required" for protected branches
- Use environment-specific secrets for staging/production

**GitLab CI**:
- Use CI/CD variables (Settings → CI/CD → Variables)
- Mark variables as "Masked" to hide in logs
- Mark variables as "Protected" for protected branches only

**Jenkins**:
- Use Credentials plugin
- Store as "Secret text" type
- Bind credentials in pipeline using `credentials()` function

**CircleCI**:
- Use project environment variables (Project Settings → Environment Variables)
- Use contexts for shared secrets across projects

### Token Caching Security

The runner caches OAuth tokens locally:

**Cache File**: `.token_cache.json`

**Security Considerations**:
- Contains access token and expiration time
- Created in working directory
- Should be added to `.gitignore`
- Automatically refreshed when expired
- Can be safely deleted to force re-authentication

**Recommendation**:
```bash
# Add to .gitignore
echo ".token_cache.json" >> .gitignore

# Clean up after CI/CD run
rm -f .token_cache.json
```

## Artifact Retention

### Storage Considerations

Artifacts (recordings, screenshots, logs, traces) are stored in S3:

**Artifact Types and Sizes**:
- **Recordings** (video/webm): 5-50 MB per execution
- **Screenshots** (image/png): 100-500 KB per step
- **Logs** (text/plain): 10-100 KB per execution
- **Traces** (application/json): 50-500 KB per step

**Storage Cost Estimation**:
```
Example: 100 executions/day with 10 steps each
- Recordings: 100 × 20 MB = 2 GB/day
- Screenshots: 100 × 10 × 200 KB = 200 MB/day
- Logs: 100 × 50 KB = 5 MB/day
- Traces: 100 × 10 × 100 KB = 100 MB/day
Total: ~2.3 GB/day = ~70 GB/month
```

### Retention Policies

Implement retention policies to manage storage costs:

**Recommended Retention Periods**:

| Artifact Type | Retention Period | Rationale |
|---------------|------------------|-----------|
| Failed execution artifacts | 90 days | Debugging and analysis |
| Passed execution artifacts | 30 days | Compliance and auditing |
| Smoke test artifacts | 7 days | Quick feedback only |
| Production test artifacts | 180 days | Regulatory compliance |

**S3 Lifecycle Policy Example**:
```json
{
  "Rules": [
    {
      "Id": "Delete old artifacts",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "artifacts/"
      },
      "Expiration": {
        "Days": 90
      }
    },
    {
      "Id": "Transition to Glacier",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "artifacts/production/"
      },
      "Transitions": [
        {
          "Days": 30,
          "StorageClass": "GLACIER"
        }
      ]
    }
  ]
}
```

### Cleanup Strategies

**Automated Cleanup** (recommended):
- Use S3 lifecycle policies for automatic deletion
- Configure in CDK/CloudFormation deployment
- Set different policies for different environments

**Manual Cleanup** (not recommended):
- Requires custom scripts
- Risk of accidental deletion
- Operational overhead

**Selective Retention**:
```python
# Example: Keep only failed execution artifacts
import boto3

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('executions')

# Query failed executions
response = table.query(
    IndexName='status-index',
    KeyConditionExpression='status = :status',
    ExpressionAttributeValues={':status': 'failed'}
)

failed_execution_ids = [item['execution_id'] for item in response['Items']]

# Delete artifacts for passed executions only
# (Keep failed execution artifacts for debugging)
```

### Artifact Access Patterns

**When to Download Artifacts**:
- Debugging failed tests
- Compliance audits
- Performance analysis
- Bug reproduction

**How to Access Artifacts**:
1. Via web UI (recommended for manual review)
2. Via API (for automated analysis)
3. Direct S3 access (for bulk operations)

**Best Practice**: Use presigned URLs for temporary access without exposing S3 credentials.

## Performance Optimization

### Parallel Execution Strategies

Run multiple test suites in parallel for faster feedback:

**GitHub Actions Example**:
```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        suite: [smoke, auth, checkout, search]
    steps:
      - name: Run ${{ matrix.suite }} tests
        run: |
          docker run --rm \
            -e OAUTH_CLIENT_ID="${{ secrets.OAUTH_CLIENT_ID }}" \
            -e OAUTH_CLIENT_SECRET="${{ secrets.OAUTH_CLIENT_SECRET }}" \
            -e OAUTH_TOKEN_ENDPOINT="${{ secrets.OAUTH_TOKEN_ENDPOINT }}" \
            -e API_ENDPOINT="${{ secrets.API_ENDPOINT }}" \
            nova-act-cicd-runner:latest \
            --suite-id ${{ vars[format('{0}_SUITE_ID', matrix.suite)] }} \
            --verbose
```

**Benefits**:
- Faster total execution time
- Independent failure isolation
- Better resource utilization

**Considerations**:
- CI/CD platform concurrency limits
- API rate limits (if applicable)
- Cost of parallel runners

### Timeout Tuning

Set appropriate timeouts based on suite size:

**Recommended Timeouts**:

| Suite Size | Recommended Timeout | Example |
|------------|---------------------|---------|
| Small (5-15 use cases) | 900s (15 min) | Smoke tests |
| Medium (15-30 use cases) | 1800s (30 min) | Feature tests |
| Large (30-100 use cases) | 3600s (1 hour) | Regression tests |
| Extra Large (100+ use cases) | 7200s (2 hours) | Full suite |

**Setting Timeout**:
```bash
docker run --rm \
  -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID" \
  -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET" \
  -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT" \
  -e API_ENDPOINT="$API_ENDPOINT" \
  nova-act-cicd-runner:latest \
  --suite-id $SUITE_ID \
  --timeout 1800
```

**Timeout Best Practices**:
- Set timeout 20-30% higher than average execution time
- Monitor execution times and adjust accordingly
- Use separate timeouts for different suite types
- Fail fast on timeout to avoid wasting resources

### Resource Allocation

Allocate sufficient resources for the runner container:

**Recommended Resources**:

| Suite Size | Memory | CPU | Rationale |
|------------|--------|-----|-----------|
| Small | 2 GB | 1 vCPU | Minimal overhead |
| Medium | 4 GB | 2 vCPU | Parallel step execution |
| Large | 8 GB | 4 vCPU | Multiple browser instances |

**Docker Resource Limits**:
```bash
docker run --rm \
  --memory=4g \
  --cpus=2 \
  -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID" \
  -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET" \
  -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT" \
  -e API_ENDPOINT="$API_ENDPOINT" \
  nova-act-cicd-runner:latest \
  --suite-id $SUITE_ID
```

**Monitoring Resource Usage**:
```bash
# Monitor container resource usage
docker stats
```

### Network Optimization

Optimize network performance for faster execution:

**Regional Considerations**:
- Run tests in the same AWS region as the API
- Use `--region` flag to specify region
- Consider latency to target application

**Example**:
```bash
# Run tests in us-west-2 for lower latency
docker run --rm \
  -e OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID" \
  -e OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET" \
  -e OAUTH_TOKEN_ENDPOINT="$OAUTH_TOKEN_ENDPOINT" \
  -e API_ENDPOINT="$API_ENDPOINT" \
  nova-act-cicd-runner:latest \
  --suite-id $SUITE_ID \
  --region us-west-2
```

### Caching Strategies

Leverage caching to reduce execution time:

**OAuth Token Caching**:
- Runner automatically caches OAuth tokens
- Cache file: `.token_cache.json`
- Reduces authentication overhead
- Automatically refreshed when expired

**Docker Image Caching**:
```yaml
# GitHub Actions - cache Docker layers
- name: Set up Docker Buildx
  uses: docker/setup-buildx-action@v2

- name: Cache Docker layers
  uses: actions/cache@v3
  with:
    path: /tmp/.buildx-cache
    key: ${{ runner.os }}-buildx-${{ github.sha }}
    restore-keys: |
      ${{ runner.os }}-buildx-
```

## Security Best Practices

### OAuth Client Management

**Create Separate Clients per Environment**:
```
- CI/CD Runner - Development
- CI/CD Runner - Staging
- CI/CD Runner - Production
```

**Benefits**:
- Isolated credentials per environment
- Easier rotation and revocation
- Better audit trail
- Reduced blast radius on compromise

**Naming Convention**:
```
{Purpose} - {Environment} ({Date})
Examples:
- CI/CD Runner - Production (2024-Q1)
- Monitoring Bot - Staging (2024-02)
- Integration Tests - Development (2024-01-15)
```

### Scope Minimization

Grant only required scopes:

**CI/CD Runner** (execution only):
```json
{
  "scopes": [
    "api/suite.read",
    "api/suite.write",
    "api/execution.write"
  ]
}
```

**Monitoring Bot** (read-only):
```json
{
  "scopes": [
    "api/suite.read",
    "api/execution.read"
  ]
}
```

**Admin Tool** (full access):
```json
{
  "scopes": [
    "api/admin"
  ]
}
```

### Network Security

**Use HTTPS Only**:
- All API endpoints must use HTTPS
- Configuration validation enforces HTTPS
- Never use HTTP in production

**Firewall Rules**:
```
Outbound (required):
- HTTPS (443) to API endpoint
- HTTPS (443) to Cognito (*.amazoncognito.com)
- HTTPS (443) to S3 (*.s3.amazonaws.com)

Inbound:
- None required (runner is client-only)
```

**VPC Considerations**:
- Run in private subnet if possible
- Use NAT Gateway for outbound access
- Restrict security group rules

### Audit Logging

Enable audit logging for compliance:

**What to Log**:
- OAuth client creation/deletion
- Test suite executions
- Artifact uploads
- Authentication attempts
- Configuration changes

**Where to Log**:
- CloudWatch Logs (AWS)
- CI/CD platform logs
- SIEM system (enterprise)

**Log Retention**:
- Security logs: 1 year minimum
- Execution logs: 90 days
- Debug logs: 30 days

### Incident Response

**Compromised Credentials**:

1. **Immediate Actions**:
   - Delete compromised OAuth client
   - Rotate all related secrets
   - Review audit logs for unauthorized access

2. **Investigation**:
   - Identify scope of compromise
   - Check for unauthorized executions
   - Review artifact access logs

3. **Remediation**:
   - Create new OAuth client with new credentials
   - Update all CI/CD pipelines
   - Document incident and lessons learned

**Example Incident Response Script**:
```bash
#!/bin/bash
# Emergency credential rotation

# 1. Delete compromised client
curl -X DELETE \
  "https://api.example.com/api/oauth-clients/$COMPROMISED_CLIENT_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 2. Create new client
NEW_CLIENT=$(curl -X POST \
  'https://api.example.com/api/oauth-clients' \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "CI/CD Runner - Production (Emergency Rotation)",
    "scopes": [
      "api/suite.read",
      "api/suite.write",
      "api/execution.write"
    ]
  }')

# 3. Extract new credentials
NEW_CLIENT_ID=$(echo $NEW_CLIENT | jq -r '.client_id')
NEW_CLIENT_SECRET=$(echo $NEW_CLIENT | jq -r '.client_secret')

echo "New Client ID: $NEW_CLIENT_ID"
echo "New Client Secret: $NEW_CLIENT_SECRET"
echo "Update CI/CD secrets immediately!"
```

### Compliance Considerations

**GDPR/Privacy**:
- Avoid storing PII in test data
- Use synthetic test data
- Implement data retention policies
- Provide data deletion mechanisms

**SOC 2/ISO 27001**:
- Enable audit logging
- Implement access controls
- Regular security reviews
- Incident response procedures

**Industry-Specific**:
- Healthcare (HIPAA): Encrypt artifacts at rest
- Finance (PCI DSS): Secure credential storage
- Government (FedRAMP): Use approved regions

## Summary

Following these best practices will help you:

- **Organize tests effectively** for maintainability and clarity
- **Manage variables securely** with proper precedence and naming
- **Handle secrets safely** with rotation and least privilege
- **Optimize performance** with parallelization and resource tuning
- **Maintain security** with proper OAuth client management and audit logging
- **Control costs** with appropriate artifact retention policies

For more information, see:
- [Configuration Reference](configuration.md)
- [Security Documentation](API.md#authentication)
- [Troubleshooting Guide](troubleshooting.md)
- [CI/CD Integration Examples](ci-cd-integration/)
