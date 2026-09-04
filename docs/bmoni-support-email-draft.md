To: developers@bkey.me
Subject: bmoni_embedded_sdk 0.0.2 (Flutter) — native dependency `me.bkey.ip:bmonisigner:1.0.0` unresolvable, blocks every Android build

Hi BMONI team,

We're building on `bmoni_embedded_sdk` for the NITHUB Innovation Fair
Hackathon and have hit a packaging issue in the published 0.0.2 release
that appears to block any Android build of the plugin, not just ours.

**The problem**

`bmoni_embedded_sdk-0.0.2/android/build.gradle.kts` declares:

    implementation("me.bkey.ip:bmonisigner:1.0.0")

but does not declare any repository that resolves it, and the artifact
does not exist in any repository a public Gradle build can reach. We
checked:

  - Maven Central search index — 0 results for `bmonisigner`
  - repo1.maven.org (live host, not the lagging search index) — 404
  - dl.google.com (Google's Maven) — 404
  - Your own reference app, `bkey-inc/bmoni-embedded-flutter-example` —
    declares the identical dependency with the identical `google()` /
    `mavenCentral()` repositories and no private repo entry, so it
    would fail identically if built fresh
  - The SDK's own `pubspec.yaml` points `repository:` at
    `github.com/bkey-inc/bmoni-embedded-flutter-sdk`, which is not
    among your org's public repositories

We also matched your reference app's exact AGP 8.11.1 / Kotlin 2.2.20
pin (needed separately, since `android { kotlinOptions { ... } }` in
the plugin's own build script is a hard script-compilation error on
AGP 9+ / newer Kotlin) and still hit the same missing-artifact failure
once dependency resolution runs.

**What we need**

Either:
  1. The Maven repository URL (and credentials, if gated) that resolves
     `me.bkey.ip:bmonisigner:1.0.0`, so we can add it to our project's
     `settings.gradle.kts`, or
  2. A corrected release of `bmoni_embedded_sdk` that either vendors
     the native library directly or points at a resolvable repository.

**Reproduction**

  1. `flutter create` a new app
  2. Add `bmoni_embedded_sdk: ^0.0.2` to `pubspec.yaml`
  3. Pin `com.android.application` to `8.11.1` and
     `org.jetbrains.kotlin.android` to `2.2.20` in `settings.gradle.kts`
     (required separately — see above)
  4. `flutter build apk --debug`
  5. Fails at `:app:checkDebugAarMetadata` — "Could not find
     me.bkey.ip:bmonisigner:1.0.0"

Happy to share our full project or a minimal repro repo if useful.
We're up against a hackathon deadline, so a quick pointer to the right
Maven repository would unblock us immediately even ahead of a formal
fix.

Thanks,
[your name]
