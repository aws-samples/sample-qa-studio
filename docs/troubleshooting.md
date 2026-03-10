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

1. **Check ECS task logs**:
   - AWS Console → ECS → Clusters
   - Find your worker task
   - View CloudWatch logs

2. **Verify SQS queue**:
   - Check messages are being processed
   - Look for dead letter queue messages

3. **Check Nova Act configuration**:
   - Verify Bedrock model access
   - Check IAM permissions for worker role
   - Verify VPC configuration if using private network

4. **Review test steps**:
   - Check for invalid instructions
   - Verify URLs are accessible
   - Test manually in browser first

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

5. **Enable debug logging**:
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

**Solutions**:

1. **Check user permissions**:
   - Verify user has access to the resource
   - Check Cognito group memberships

2. **Verify OAuth scopes**:
   - For CLI: User must have appropriate permissions
   - For API clients: Client must have required scopes

3. **Contact administrator**:
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
- High ECS or Bedrock costs

**Solutions**:

1. **Review execution frequency**:
   - Reduce unnecessary test runs
   - Use test suites instead of individual tests

2. **Optimize test suites**:
   - Remove duplicate tests
   - Combine similar tests

3. **Check artifact retention**:
   - Configure S3 lifecycle policies
   - Delete old artifacts

4. **Monitor usage**:
   - Set up CloudWatch alarms
   - Review Cost Explorer regularly

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

**Worker Logs**:
- AWS Console → ECS → Tasks
- Click on task → Logs tab
- View CloudWatch logs

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
