pluginManagement {
    val flutterSdkPath =
        run {
            val properties = java.util.Properties()
            file("local.properties").inputStream().use { properties.load(it) }
            val flutterSdkPath = properties.getProperty("flutter.sdk")
            require(flutterSdkPath != null) { "flutter.sdk not set in local.properties" }
            flutterSdkPath
        }

    includeBuild("$flutterSdkPath/packages/flutter_tools/gradle")

    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

plugins {
    id("dev.flutter.flutter-plugin-loader") version "1.0.0"
    // Pinned below `flutter create`'s default (AGP 9.1.0 / Kotlin 2.4.0).
    // bmoni_embedded_sdk 0.0.2's own android/build.gradle.kts uses the
    // classic `android { kotlinOptions { jvmTarget = ... } }` DSL, which
    // newer AGP/Kotlin raise from a deprecation warning to a hard
    // script-compilation error. Flutter 3.47.2 in turn enforces its own
    // floor: AGP >= 8.11.1, Kotlin (KGP) >= 2.2.20. Both pins sit exactly at
    // Flutter's floor — the narrowest window that satisfies Flutter's
    // validation while staying below the versions that broke the SDK's
    // build script.
    id("com.android.application") version "8.11.1" apply false
    id("org.jetbrains.kotlin.android") version "2.2.20" apply false
}

include(":app")
