# BharatAgriLens · Mobile Release Runbook

Everything you need to ship Android and iOS builds. Read end-to-end the
first time; reference specific sections on subsequent releases.

## What you're shipping

A single React codebase that runs in three contexts:

- **Web**: the Vite-built SPA hosted on Railway at
  `https://balweb-production.up.railway.app/`
- **Android**: the same SPA bundled inside a Capacitor WebView, signed
  as a `.aab` (Android App Bundle) and published to Google Play Store
- **iOS**: same again, bundled inside a Capacitor WebView, signed as a
  `.ipa` and published to Apple App Store

Native capabilities (camera, gallery, preferences storage) flow through
Capacitor plugins; the JS calls a thin shim
(`apps/web/src/lib/camera.ts`, `apps/web/src/lib/platform.ts`) that
picks the right backend at runtime.

## One-time prerequisites

### For Android (works on Windows / Mac / Linux)

1. **Node.js 20+** and **pnpm 9+** (you already have these)
2. **JDK 21** (Temurin recommended). Verify: `java -version`
3. **Android Studio** — download from
   <https://developer.android.com/studio>. During the first launch it
   installs the Android SDK (~3 GB).
4. **A Google Play Console account** — one-time $25 at
   <https://play.google.com/console/signup>

### For iOS (Mac only)

1. **macOS 13 or later** with **at least 30 GB free disk**
2. **Xcode 15+** from the Mac App Store (~15 GB)
3. **CocoaPods** — `sudo gem install cocoapods` (or `brew install cocoapods`)
4. **An Apple Developer account** — $99/year at
   <https://developer.apple.com/programs/enroll/>

If you don't have a Mac, you can still build iOS via CI (see the
`mobile.yml` workflow's `ios-archive` job which uses GitHub-hosted
macOS runners). Local iOS testing still requires Xcode though, so
plan for at least occasional Mac access.

## Bootstrap (one-time, after cloning the repo)

```bash
# Install all workspace deps including the new Capacitor packages
pnpm install

# Generate the Android Studio project
cd apps/mobile
npx cap add android

# (Mac only) Generate the Xcode project
npx cap add ios

# Commit the generated native projects
git add apps/mobile/android apps/mobile/ios
git commit -m "chore(mobile): add Android + iOS Capacitor platforms"
```

After this, `apps/mobile/android/` and `apps/mobile/ios/` are tracked
in git. Future devs cloning the repo skip the `cap add` step.

## Daily dev loop

You edit `apps/web/src/**` as normal. To see your changes in the
mobile shell:

```bash
# Build the web app + sync into both native projects
cd apps/mobile
pnpm sync
```

To run on a device:

```bash
# Android — plug in an Android phone with USB debugging on, OR start
# an emulator from Android Studio
pnpm run:android

# iOS — plug in an iPhone (and trust the Mac), OR pick a simulator
pnpm run:ios
```

To open the IDE for debugging:

```bash
pnpm open:android      # Android Studio
pnpm open:ios          # Xcode (Mac only)
```

### Live-reload dev (optional, faster iteration)

For UI tweaks you don't want to rebuild for every time, point the
Capacitor WebView at your local Vite dev server:

1. Find your laptop's LAN IP (e.g. `192.168.1.42`)
2. Edit `apps/mobile/capacitor.config.ts` — uncomment the `server`
   block and put your LAN IP there
3. Start `pnpm --filter @bal/web dev` (Vite on 5173)
4. Run `pnpm run:android` — the app loads from your Vite dev server,
   hot-reload works as normal
5. **Revert the `server` block before building for release** — bundled
   release builds need the local assets, not a dev server URL

## Production Android release

### One-time: generate a release keystore

```bash
keytool -genkey -v \
  -keystore bal-release.keystore \
  -alias bal \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000

# Answer the prompts. The CN can be your name or your org's name.
# Pick a strong passphrase you'll remember (or store in a password
# manager).
```

⚠️ **This file is irreplaceable.** Losing it means you can't update the
Play Store app anymore — you'd have to publish a new app with a new
package ID, losing all reviews/installs. Back it up to at least two
places (password manager + offline drive).

Store the keystore outside the repo (e.g. `~/Documents/keys/`). The
`.gitignore` in `apps/mobile/` blocks `*.keystore` so accidental
commits don't expose it.

### Build a signed AAB locally

```bash
cd apps/mobile
pnpm sync:android
pnpm open:android
# In Android Studio: Build menu -> Generate Signed Bundle / APK
#   -> Android App Bundle (AAB, what Play wants)
#   -> Browse to your bal-release.keystore, enter passwords
#   -> Pick release variant
# AAB lands at android/app/build/outputs/bundle/release/app-release.aab
```

### Build a signed AAB in CI

Add four GitHub secrets to the repo:

```
ANDROID_KEYSTORE_B64   = base64-encoded contents of bal-release.keystore
ANDROID_KEYSTORE_PASS  = the keystore password you set
ANDROID_KEY_ALIAS      = bal
ANDROID_KEY_PASS       = the alias's password (often same as keystore)
```

To encode the keystore on Windows PowerShell:

```powershell
$bytes = [IO.File]::ReadAllBytes("C:\path\to\bal-release.keystore")
[Convert]::ToBase64String($bytes) | Set-Clipboard
# Then paste the value into the ANDROID_KEYSTORE_B64 secret
```

Push a release tag — the `android-release` job in `mobile.yml` runs
and uploads a signed `.aab` as a workflow artifact.

### Play Store submission

1. <https://play.google.com/console> -> Create app
2. Fill in: app name (BharatAgriLens), default language (English), App
   or Game (App), Free or Paid (Free)
3. Required declarations: privacy policy URL, app access, ads,
   content rating questionnaire, target audience and content,
   data safety
4. **Internal testing** track first: upload the AAB, add yourself +
   2-3 testers via a Google Group, get the opt-in link, install on
   your phone. Confirm camera, sign-in, and analyse work end-to-end.
5. Promote to **Production** when ready. Review takes 1-3 days for
   first submission, hours for subsequent updates.

## Production iOS release

### One-time: Apple Developer setup

1. Enroll at <https://developer.apple.com/programs/enroll/>. Personal
   ($99/year) or Organisation ($99/year + D-U-N-S number — get this
   for free at <https://www.dnb.com/duns-number/get-a-duns.html>).
2. Once enrolled, in <https://developer.apple.com/account>:
   - Identifiers -> register the bundle ID `in.bharatagrilens.app`
   - Certificates -> create a Distribution certificate (download .cer)
   - Profiles -> create an App Store provisioning profile for the
     bundle ID (download .mobileprovision)

### Build a signed IPA

1. Open the project in Xcode: `cd apps/mobile && pnpm open:ios`
2. In Xcode, select **App** target -> **Signing & Capabilities**:
   - Team: pick your Apple Developer team
   - Bundle Identifier: `in.bharatagrilens.app`
   - "Automatically manage signing": ON (easiest) OR import the
     provisioning profile manually
3. Product menu -> Archive (Xcode builds a release archive)
4. Window menu -> Organizer -> Distribute App -> App Store Connect ->
   Upload

### App Store Connect submission

1. <https://appstoreconnect.apple.com> -> My Apps -> "+" -> New App
2. Select bundle ID `in.bharatagrilens.app`
3. Fill in: name, primary language, SKU (any unique string per app),
   user access (full access for owner)
4. **TestFlight tab**: pick the build you uploaded -> add yourself
   as an internal tester -> install via TestFlight on your iPhone ->
   verify everything
5. **App Store** tab: fill in description, screenshots (6.7", 6.5",
   5.5" required), keywords, support URL, marketing URL, privacy
   policy URL, age rating
6. App Review will check: camera permission text in Info.plist (we
   set this in `capacitor.config.ts`), sign-in flow demo (provide a
   test account in the Reviewer Notes), in-app purchases (we have
   none — declare that)
7. Submit for review. First review usually takes 24-72 hours.

## Common issues + fixes

| Symptom | Cause | Fix |
|---|---|---|
| Android: `SDK location not found` | `local.properties` missing | In Android Studio, the IDE writes this on first launch. Or set `$ANDROID_HOME` env var. |
| Android: `Failed to apply plugin 'com.android.application'` | Gradle version mismatch | `cd apps/mobile && npx cap sync android` regenerates the gradle wrapper |
| iOS: `'@capacitor/camera' Pods incompatible` | CocoaPods cache stale | `cd ios/App && pod install --repo-update` |
| iOS: app crashes immediately on launch | Missing Info.plist permission descriptions | Verify `capacitor.config.ts` has the `Camera.permissions` block, then `pnpm sync:ios` |
| Web works, Android shows blank screen | `webDir` path wrong, or web build missing | Run `pnpm --filter @bal/web build` first, then `pnpm sync` |
| Camera plugin shows "no implementation found" on web | Expected | The shim falls back to `<input type="file">` on web; no action needed |
| CORS error on api calls from Android app | api's `CORS_ALLOWED_ORIGINS` doesn't include the Android WebView origin | Add `https://localhost`, `capacitor://localhost`, and (for iOS) `ionic://localhost` to the api's `CORS_ALLOWED_ORIGINS` env var |

## Updating `VITE_API_BASE_URL`

The Android / iOS bundles bake the API base URL at build time (Vite
inlines `VITE_*` env vars into the JS bundle). To change which API the
mobile app talks to:

1. Set `VITE_API_BASE_URL` env var (e.g. via a `.env.production` file
   in `apps/web/` or in CI variables)
2. Rebuild the web app: `pnpm --filter @bal/web build`
3. Sync into mobile: `cd apps/mobile && pnpm sync`
4. Re-archive and re-upload to Play Store / App Store Connect

If you need to change the URL after release without forcing users to
update, consider proxying via your existing domain — keep
`api-production-d64e.up.railway.app` stable and have it forward to
whatever backend you have.

## Versioning

Bump both the marketing version (visible in stores) and the build
number (used by stores internally) on every release.

**Android** — `apps/mobile/android/app/build.gradle`:
```
versionCode 2        // integer, must increment every Play upload
versionName "0.2.0"  // semver, shown in store
```

**iOS** — `apps/mobile/ios/App/App/Info.plist` (or in Xcode under
General -> Identity):
```
CFBundleShortVersionString = 0.2.0
CFBundleVersion             = 2
```

Both can be edited in their respective IDEs or scripted from a
post-version-bump hook. Keep them in sync with `apps/mobile/package.json`'s
`version` for sanity.

## Phase 2 features worth adding post-launch

| Feature | Plugin | Approx effort |
|---|---|---|
| SMS OTP auto-fill (Android Smart OTP) | `@capacitor-firebase/authentication` or `@capacitor-community/sms-receive` | half day |
| Push notifications (diagnosis ready) | `@capacitor/push-notifications` + FCM (Android), APNs (iOS) | 1-2 days |
| Geolocation (auto-tag scans with farm coords) | `@capacitor/geolocation` | half day |
| Background image upload queue (offline-first) | `@capacitor/background-runner` + IndexedDB | 1-2 days |
| App icons + splash screens | `@capacitor/assets` | half day |
| Better voice recording for chat | `@capacitor-community/speech-recognition` | half day |

These all reuse the same shim pattern: add the plugin, write a thin
platform-aware wrapper in `apps/web/src/lib/`, branch on
`isNativePlatform()` for the fallback.
