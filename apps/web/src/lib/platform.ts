/**
 * Runtime platform detection.
 *
 * The same React bundle ships to three contexts:
 *   1. Plain browser  (Railway-hosted web app)
 *   2. Capacitor on Android  (apps/mobile + Android Studio build)
 *   3. Capacitor on iOS      (apps/mobile + Xcode build)
 *
 * Code that needs to branch — e.g. the camera shim picks the native
 * plugin vs. the HTML <input type="file"> — calls ``isNativePlatform()``
 * to find out which environment it's in. The shims fall through to the
 * web-friendly implementation when not native, so plain web builds keep
 * working unchanged.
 *
 * The Capacitor import is dynamic / guarded so the package is optional
 * — if ``@capacitor/core`` isn't installed (e.g. the web app builds in
 * an environment that doesn't include the mobile deps), we fall back to
 * "not native" and everything still works.
 */

let _isNative: boolean | null = null;

export function isNativePlatform(): boolean {
  if (_isNative !== null) return _isNative;
  try {
    // Capacitor exposes window.Capacitor.isNativePlatform() at runtime
    // inside the WebView; on plain browser there's no such global.
    const cap = (globalThis as { Capacitor?: { isNativePlatform?: () => boolean } }).Capacitor;
    _isNative = !!cap?.isNativePlatform?.();
  } catch {
    _isNative = false;
  }
  return _isNative;
}

export function getPlatform(): 'web' | 'android' | 'ios' {
  try {
    const cap = (globalThis as {
      Capacitor?: { getPlatform?: () => 'web' | 'android' | 'ios' };
    }).Capacitor;
    return cap?.getPlatform?.() ?? 'web';
  } catch {
    return 'web';
  }
}
