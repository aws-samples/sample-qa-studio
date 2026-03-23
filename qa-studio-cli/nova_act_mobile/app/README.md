# Mobile App Configuration

App identity configuration for Nova Act mobile automation. Infrastructure-agnostic — used by both local Appium and Device Farm flows.

## Key Classes

### `MobileAppConfig`

Dataclass that identifies which mobile app to launch and interact with. Holds platform-specific identifiers (package/activity for Android, bundle ID for iOS) that the DeviceFarm and Mobile actuators use to start the correct app and that `MobileActuator.app_url()` uses for URL-based app switching. Use the `for_android()` and `for_ios()` factory methods to construct. See [the parent example](../../README.md) for usage.

## Sample App

`samples/aws-device-farm-sample/` contains a pre-built Android APK from the [AWS Device Farm sample app](https://github.com/aws-samples/aws-device-farm-sample-app-for-android). This is the default app used when `main.py` is run with no arguments.
