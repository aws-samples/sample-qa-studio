# Mobile Actuators

[Appium](https://appium.io/)-based mobile actuators that implement the Nova Act `BrowserActuatorBase` interface for iOS and Android.

## Structure

```
actuation/
├── mobile_actuator.py          # MobileActuator — core Appium actuator
├── device_farm_actuator.py     # DeviceFarmActuator — adds AWS Device Farm lifecycle
├── appium_instance_manager.py  # Appium WebDriver lifecycle management
├── appium_instance_options.py  # Pydantic config for Appium capabilities
├── appium_driver_manager.py    # Abstract base for driver access
└── util/
    ├── mobile_click.py         # Tap / double-tap / long-press via W3C Actions
    ├── mobile_scroll.py        # Swipe gestures
    ├── mobile_type.py          # Keyboard input
    ├── mobile_observation.py   # Screenshot + UI hierarchy parsing
    ├── mobile_app_management.py # App launch, terminate, deep links
    └── mobile_wait.py          # Idle detection and smart waiting
```

## Key Classes

### `MobileActuator`

Infrastructure-agnostic Appium actuator. Works with any Appium server, whether local, AWS Device Farm, or a third-party cloud provider. Constructed with [`AppiumInstanceOptions`](appium_instance_options.py) and provides `app_url()` for encoding mobile app identifiers as Nova Act-compatible URLs. See [mobile_actuator.py](mobile_actuator.py) for details.

#### Using your own Appium server

To use `MobileActuator` with an Appium server:

```python
# Define app identity — change to match your app
app = MobileAppConfig.for_android(
    app_package="com.android.settings",  # your app's package name
    app_activity=".Settings",  # your app's launch activity
)

# iOS alternative:
# app = MobileAppConfig.for_ios(bundle_id="com.example.myapp")

# Configure Appium connection
appium_options = AppiumInstanceOptions(
    platform=app.platform,
    device_name="emulator-5554",  # your device name or emulator ID
    platform_version="15",  # your device's OS version
    app_package=app.app_package,
    app_activity=app.app_activity,
)

with NovaAct(
    actuator=MobileActuator(appium_options=appium_options),
    starting_page=MobileActuator.app_url(app.app_identifier),
) as nova:
    nova.act("tap the login button")
```

`AppiumInstanceOptions` defaults to `http://127.0.0.1:4723` for the Appium server URL. Set `appium_server_url` to connect to a remote server. See [`appium_instance_options.py`](appium_instance_options.py) for the full list of fields including `udid`, `app_path`, and `additional_capabilities`.

### `DeviceFarmActuator`

Extends `MobileActuator` to provision and tear down an AWS Device Farm session automatically. Takes a `MobileAppConfig` for app identity and an optional `DeviceFarmUploadConfig` for the app binary. See the [parent example](../../README.md) for usage.

## Platform Notes

- **Android** — Uses [UIAutomator2](https://github.com/appium/appium-uiautomator2-driver)
- **iOS** — Uses [XCUITest](https://github.com/appium/appium-xcuitest-driver)
