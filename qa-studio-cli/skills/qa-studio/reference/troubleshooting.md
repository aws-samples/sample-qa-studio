# Troubleshooting

## Common Errors and Solutions

### Authentication Errors

#### Error: Not authenticated

**Cause:** CLI token is missing or expired

**Solution:**
```bash
qa-studio login
```

---

#### Error: OAuth authentication failed: 401

**Cause:** Invalid OAuth client credentials (CI/CD)

**Solution:**
1. Verify `OAUTH_CLIENT_ID` and `OAUTH_CLIENT_SECRET` are correct
2. Check OAuth client exists in QA Studio (Settings → OAuth Clients)
3. Verify token endpoint URL is correct

---

### AWS Errors

#### Error: No valid AWS session found

**Cause:** AWS credentials not configured or expired

**Solution:**
```bash
# Verify credentials
aws sts get-caller-identity

# Re-authenticate if needed
aws sso login --profile your-profile

# Or set environment variables
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
```

---

#### Error: Access denied to Bedrock

**Cause:** AWS credentials lack Bedrock permissions

**Solution:**
1. Verify IAM user/role has `bedrock:InvokeModel` permission
2. Check Nova Act model is available in the region
3. Verify region supports Nova Act

---

### Test Execution Errors

#### Error: Use case not found

**Cause:** Test ID doesn't exist or was deleted

**Solution:**
```bash
qa-studio tests list  # Verify test ID
```

---

#### Error: Step failed - Element not found

**Cause:** Target element missing, page didn't load, or UI changed

**Solution:**
1. Verify base URL is correct and accessible:
   ```bash
   curl http://localhost:3000
   ```

2. Review video recording:
   ```bash
   qa-studio run --usecase-id <id> --keep-artifacts
   # Open ~/.qa-studio/artifacts/<id>/recording.webm
   ```

3. Check if UI has changed since test was created

4. Re-run with verbose logging:
   ```bash
   qa-studio run --usecase-id <id> --verbose
   ```

5. Update test steps if UI changed

---

#### Error: Execution timed out

**Cause:** Test exceeded global timeout (default: 3600 seconds)

**Solution:**
```bash
qa-studio run --usecase-id <id> --timeout 7200
```

---

### Configuration Errors

#### Error: Configuration not found

**Cause:** CLI not configured

**Solution:**
```bash
qa-studio configure
```

---

#### Error: Runner dependencies not installed

**Cause:** `qa-studio[runner]` extras not installed

**Solution:**
```bash
pip install qa-studio[runner]
```

---

#### Error: Skills not installed

**Cause:** Kiro skills not installed

**Solution:**
```bash
qa-studio setup
```

---

### Suite Errors

#### Error: Suite not found

**Cause:** Suite ID doesn't exist or was deleted

**Solution:**
```bash
qa-studio suites list  # Verify suite ID
```

---

#### Error: No usecases in suite

**Cause:** Suite has no tests added

**Solution:**
```bash
qa-studio suites add-tests <suite-id> <test-id-1> <test-id-2>
```

---

## Debugging Workflow

### Step 1: Enable Verbose Logging

```bash
qa-studio run --usecase-id <id> --verbose
```

### Step 2: Keep Artifacts Locally

```bash
qa-studio run --usecase-id <id> --keep-artifacts
```

### Step 3: Review Artifacts

1. **Video recording:** `~/.qa-studio/artifacts/<id>/recording.webm`
   - Watch full browser session
   - Identify where test fails visually

2. **Execution log:** `~/.qa-studio/artifacts/<id>/execution.log`
   - Detailed step-by-step logs
   - Error messages and stack traces

3. **Screenshots:** `~/.qa-studio/artifacts/<id>/screenshot_step_N.png`
   - Browser state at each step
   - Verify elements are visible

### Step 4: Test Against Localhost

```bash
# Start local server
npm run dev

# Run test locally
qa-studio run --usecase-id <id> \
  --base-url http://localhost:3000 \
  --verbose \
  --keep-artifacts
```

### Step 5: Verify Prerequisites

```bash
# Check authentication
qa-studio status

# Check AWS credentials
aws sts get-caller-identity

# Check local server
curl http://localhost:3000
```

---

## Performance Issues

### Slow Test Execution

**Causes:**
- Network latency
- Slow page load times
- Complex page interactions

**Solutions:**
1. Increase timeout: `--timeout 7200`
2. Optimize test steps (remove unnecessary waits)
3. Use faster region (closer to target application)

---

### High Memory Usage

**Causes:**
- Large video recordings
- Many screenshots
- Long-running tests

**Solutions:**
1. Clean up artifacts after execution (don't use `--keep-artifacts`)
2. Split long tests into smaller tests
3. Use suite execution with parallel runs

---

## Getting Help

### Check Status

```bash
qa-studio status
```

### Review Logs

```bash
qa-studio run --usecase-id <id> --verbose
```

### Test Configuration

```bash
# Verify configuration
cat ~/.qa-studio/config.json

# Verify token
cat ~/.qa-studio/token.json
```

### Contact Support

If issues persist:
1. Collect verbose logs
2. Save artifacts (video, logs)
3. Note error messages
4. Contact your QA Studio administrator

---

## Next Steps

- **Best practices:** [📚 Best Practices](./best-practices.md)
- **CI/CD integration:** [🔄 CI/CD Integration](./ci-cd-integration.md)
- **Step types:** [🎯 Step Types](./step-types.md)
