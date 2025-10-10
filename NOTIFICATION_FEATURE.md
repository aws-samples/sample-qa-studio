# Email Notification Feature

This document describes the email notification feature that sends alerts when scheduled executions fail.

## Overview

The notification system consists of user-specific subscriptions:

### User Subscriptions (Scheduled Executions Only)
- **Per-Usecase Subscriptions**: Users can subscribe to specific usecases for failure notifications
- **Scheduled Only**: Notifications are only sent for scheduled execution failures
- **User-Based**: Uses JWT token email for subscription management
- **DynamoDB Storage**: Subscriptions stored with PK `USECASE#{usecase_id}` and SK `NOTIFICATION#{uuid}`
- **Frontend Integration**: Subscribe/unsubscribe button on usecase detail pages
- **SQS Queue**: `{base_name}_notifications` queue for processing notification messages
- **SES Integration**: Amazon Simple Email Service for sending notification emails

## Architecture

### Infrastructure Components

1. **SQS Notification Queue**: `{base_name}_notifications`
   - Receives messages when executions fail
   - Triggers the send notification lambda

2. **Lambda Functions**:
   - `send_notification`: Processes SQS messages and sends emails via SES
   - `subscribe_usecase`: Subscribes current user to usecase failure notifications
   - `unsubscribe_usecase`: Unsubscribes current user from usecase notifications
   - `get_usecase_subscription`: Gets subscription status for current user and usecase

3. **DynamoDB Records**:

   **User Subscriptions:**
   - **PK**: `USECASE#{usecase_id}`
   - **SK**: `NOTIFICATION#{uuid}`
   - **email**: User's email from JWT token
   - **createdAt**: Timestamp when subscription was created

### Workflow

1. **Execution Failure**: When an execution status is updated to "failed" via the `update_execution` lambda
2. **Queue Message**: A notification message is sent to the SQS queue containing:
   ```json
   {
     "usecase_id": "uuid",
     "execution_id": "uuid"
   }
   ```
3. **Email Processing**: The `send_notification` lambda:
   - Retrieves usecase and execution details from DynamoDB
   - **If execution is scheduled**: Gets user subscriptions for the usecase and sends notifications
   - **If execution is not scheduled**: Skips notification (only scheduled executions trigger notifications)

### Email Content

The notification email includes:
- Usecase name and description
- Execution ID and status
- Trigger type (OnDemand, Scheduled, etc.)
- Start and completion timestamps
- Starting URL
- HTML and text versions

## API Endpoints

### User Subscription Management

#### Get Subscription Status
```
GET /usecase/{id}/subscription
```
Returns subscription status for the current user and usecase:
```json
{
  "is_subscribed": true,
  "email": "user@example.com"
}
```

#### Subscribe to Usecase
```
POST /usecase/{id}/subscription
```
Subscribes the current user to failure notifications for the specified usecase.
Returns subscription status:
```json
{
  "is_subscribed": true,
  "email": "user@example.com"
}
```

#### Unsubscribe from Usecase
```
DELETE /usecase/{id}/subscription
```
Unsubscribes the current user from failure notifications for the specified usecase.
Returns subscription status:
```json
{
  "is_subscribed": false,
  "email": "user@example.com"
}
```

## Frontend Usage

### User Subscriptions
1. **Access**: Navigate to any usecase detail page
2. **Subscribe**: Click "Subscribe to Failures" button to receive notifications for scheduled execution failures
3. **Unsubscribe**: Click "Unsubscribe" button to stop receiving notifications
4. **Status**: Button automatically shows current subscription status

The subscription button:
- Shows current subscription status (subscribed/not subscribed)
- Uses different visual styles for subscribed vs unsubscribed states
- Includes notification icons for better UX
- Handles loading states during API calls

## Configuration Requirements

### SES Setup
- Configure Amazon SES in your AWS account
- Verify the sender email address (currently set to `noreply@example.com`)
- Ensure SES is out of sandbox mode for production use

### IAM Permissions
The following permissions are automatically configured:
- Lambda execution roles have DynamoDB read/write access
- Send notification lambda has SES send email permissions
- Update execution lambda has SQS send message permissions
- Subscription lambdas have DynamoDB read/write access for user subscriptions

### JWT Token Requirements
- User subscription features require valid JWT tokens with email claims
- Email is extracted from the `email` field in JWT token claims
- Authentication is handled automatically by API Gateway Cognito authorizer

## Deployment

The notification feature is automatically deployed when you deploy the CDK stack:

```bash
npm run build
cdk deploy
```

## Monitoring

- **CloudWatch Logs**: Each lambda function logs to CloudWatch
- **SQS Metrics**: Monitor queue depth and message processing
- **SES Metrics**: Track email delivery and bounce rates
- **DynamoDB Metrics**: Monitor read/write capacity and throttling

## Troubleshooting

### Common Issues

1. **Emails not sending**:
   - Check SES configuration and sender verification
   - Verify SES is out of sandbox mode
   - Check CloudWatch logs for the send notification lambda

2. **Global notifications not triggered**:
   - Verify execution status is being set to "failed"
   - Check SQS queue for messages
   - Review update execution lambda logs

3. **User subscriptions not working**:
   - Verify JWT token contains email claim
   - Check subscription lambda logs for authentication errors
   - Confirm user is properly authenticated

4. **Subscription button not showing correct status**:
   - Check browser console for API errors
   - Verify get subscription status lambda is working
   - Confirm DynamoDB permissions for subscription lambdas

5. **Frontend errors**:
   - Check browser console for API errors
   - Verify API Gateway endpoints are accessible
   - Confirm authentication tokens are valid

### Logs Location
- Lambda logs: `/aws/lambda/{base_name}-{function_name}`
- API Gateway logs: Check API Gateway console
- SQS metrics: CloudWatch SQS dashboard

## Testing

Use the provided test script to verify the notification system:

```bash
# List configured global emails
python3 test_notifications.py --base-name your-base-name --list-emails

# Send test notification
python3 test_notifications.py --base-name your-base-name --test-notification --usecase-id test-id --execution-id test-exec-id
```

## Security Considerations

- User subscriptions are tied to authenticated users via JWT tokens
- Email addresses are extracted from verified JWT claims
- All API endpoints require proper authentication
- DynamoDB access is restricted to appropriate lambda functions
- SES permissions are limited to sending emails only