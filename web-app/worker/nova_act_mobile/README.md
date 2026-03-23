# Nova Act Mobile Automation Package Example

Mobile actuation package for Nova Act on iOS and Android. Provides Appium-based actuators that implement the Nova Act `BrowserActuatorBase` interface, plus AWS Device Farm integration for remote device provisioning.

## Structure

```
nova_act_mobile/
├── platform.py         # Platform enum (Android / iOS)
├── actuation/          # Mobile actuator implementations for Appium and Device Farm
├── app/                # Infrastructure-agnostic mobile app config and sample mobile app
└── device_farm/        # AWS Device Farm client and upload config
```

## Key Classes

### `Platform`

`StrEnum` identifying the target mobile platform (`ANDROID`, `IOS`). Provides properties for Appium automation name, Device Farm upload type, and app file extension. See [`platform.py`](platform.py).

### `MobileActuator`

Infrastructure-agnostic Appium actuator. See [`actuation/`](actuation/README.md) for details.

### `DeviceFarmActuator`

Extends `MobileActuator` with automatic Device Farm session lifecycle. See [`actuation/`](actuation/README.md) for details.

## Subpackages

- [`actuation/`](actuation/README.md) — Appium actuator implementations
- [`app/`](app/README.md) — `MobileAppConfig` for app identity
- [`device_farm/`](device_farm/README.md) — AWS Device Farm client and upload config
