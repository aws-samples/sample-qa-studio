# Backup Vault Cleanup Lambda

## Purpose

This Lambda function is a CloudFormation custom resource that automatically cleans up AWS Backup recovery points before the backup vault is deleted during stack destruction.

## Problem It Solves

AWS Backup Vaults cannot be deleted if they contain recovery points (backups). Without this cleanup function, CloudFormation stack deletion would fail when trying to delete the backup vault, leaving resources in an inconsistent state.

## How It Works

1. **On Stack Creation/Update**: No action is taken
2. **On Stack Deletion**: 
   - Lists all recovery points in the backup vault
   - Deletes each recovery point
   - Waits for deletions to complete (up to 10 minutes)
   - Returns success to CloudFormation
   - CloudFormation then proceeds to delete the vault

## Configuration

The Lambda function is configured with:
- **Runtime**: Python 3.13
- **Architecture**: ARM64
- **Timeout**: 15 minutes
- **Memory**: 256 MB

## IAM Permissions Required

The Lambda function requires the following AWS Backup permissions:
- `backup:ListRecoveryPointsByBackupVault`
- `backup:DeleteRecoveryPoint`
- `backup:DescribeRecoveryPoint`

## Usage in CDK

The function is automatically integrated into the storage stack as a custom resource:

```typescript
const cleanupProvider = new Provider(this, 'BackupVaultCleanupProvider', {
  onEventHandler: cleanupLambda,
});

const cleanupResource = new CustomResource(this, 'BackupVaultCleanup', {
  serviceToken: cleanupProvider.serviceToken,
  properties: {
    BackupVaultName: backupVault.backupVaultName,
  },
});
```

## Logging

All operations are logged to CloudWatch Logs for debugging and audit purposes.

## Error Handling

- If recovery points cannot be deleted within the timeout, the function returns a partial success status
- CloudFormation will still proceed with vault deletion
- All errors are logged to CloudWatch Logs

## Testing

To test the cleanup function:
1. Deploy the stack with backups enabled
2. Wait for at least one backup to be created
3. Destroy the stack
4. Check CloudWatch Logs to verify recovery points were deleted
5. Verify the backup vault was successfully deleted
