# AWS Device Farm Sample App

Pre-built debug APK of the [AWS Device Farm Android Reference App](https://github.com/aws-samples/aws-device-farm-sample-app-for-android) for use as a default test target.

## App Details

- Package: `com.amazonaws.devicefarm.android.referenceapp`
- Activity: `com.amazonaws.devicefarm.android.referenceapp.Activities.MainActivity`

## Modifications from Original

The following changes were made to the original source to support modern Android and AWS Device Farm requirements:

- Updated Gradle plugin from `2.3.2` to `3.5.4` and Gradle wrapper from `4.1` to `5.4.1`
- Replaced `jcenter()`/`mavenLocal()` repositories with `google()` and `mavenCentral()`
- Added `includeCompileClasspath true` for annotation processor options (ButterKnife compatibility)
- Updated `minSdkVersion` from 10 to 24
- Updated `targetSdkVersion` from 22 to 34
- Added `android:exported="true"` to `MainActivity` (required for SDK 31+)
- Added null safety checks for `getSupportActionBar()`, `getCurrentFocus()`, `getArguments()`, `RadioButton` lookup, and `camera` across multiple Activities and Fragments
- DatePicker now initializes to today's date instead of a hardcoded date
- Added `Input_EditTextFragment` with submit button and result display, replacing the previous static layout
- Added string resources `text_input_submitted` and `text_input_submitted_empty`

## License

Apache 2.0 — see [LICENSE.txt](./LICENSE.txt). Original source: https://github.com/aws-samples/aws-device-farm-sample-app-for-android
