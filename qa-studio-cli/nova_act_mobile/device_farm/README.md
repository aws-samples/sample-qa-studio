# Device Farm Client

AWS Device Farm client for Nova Act mobile automation. Handles project/device discovery, app upload, and remote access session lifecycle. Used internally by [`DeviceFarmActuator`](../actuation/README.md).

## Structure

```
device_farm/
├── client.py        # DeviceFarmClient — all Device Farm API operations
├── config.py        # DeviceFarmConfig — constants (timeouts, default app)
└── upload_config.py # DeviceFarmUploadConfig — app upload configuration (name, path)
```

## Key Classes

### `DeviceFarmClient`

Stateless wrapper around the boto3 Device Farm client. Handles project/device discovery, app upload with deduplication, Remote Access Session creation and polling, and session teardown. The main entry point is `setup_session()`. See [client.py](client.py) for details.

### `DeviceFarmUploadConfig`

App upload configuration, separate from app identity. Pass `app_name` and `app_path` for new uploads, or `app_arn` to reuse an existing upload.

### `DeviceFarmSessionResult`

Dataclass returned by `setup_session()` containing the Appium endpoint URL, session ARN, device name, and platform version.

## Notes

- Device Farm is only available in `us-west-2`. The region is hardcoded.
- App uploads are deduplicated by filename. Set `force_upload=True` to bypass.
- If session setup fails after creation (timeout, terminal state, Ctrl+C), the session is automatically stopped before the error propagates.
