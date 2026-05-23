/**
 * Camera shim — single API for grabbing an image from the user.
 *
 * On Capacitor (Android / iOS) we use ``@capacitor/camera`` for proper
 * native camera access: autofocus, native gallery picker, photo
 * compression handled by the OS. On plain web we fall back to a hidden
 * ``<input type="file" accept="image/*" capture="environment">`` so the
 * page still works in any browser, including desktop.
 *
 * Returned File is a standard ``File`` object the existing upload code
 * (``api.uploads.direct``) can hand straight to FormData — no API
 * changes required downstream.
 *
 * Capacitor plugin imports are lazy + guarded so a plain web build that
 * doesn't have ``@capacitor/camera`` installed still type-checks and
 * runs; we just always take the web fallback path.
 */

import { isNativePlatform } from './platform';

/** Source of the image — defaults to letting the user choose. */
export type CameraSource = 'prompt' | 'camera' | 'gallery';

export interface PickImageOptions {
  /** Max edge length the OS resizes to before returning. Defaults to 2048. */
  maxDimension?: number;
  /** JPEG quality (0-100). Defaults to 85 — good balance for plant photos. */
  quality?: number;
  /** Where to take the image from. Defaults to ``prompt``. */
  source?: CameraSource;
  /** Suggested filename when the user picks from gallery. */
  filename?: string;
}

/**
 * Open the platform's native camera (or web file picker), wait for the
 * user to capture / select an image, return it as a standard File.
 *
 * Throws if the user cancels or denies permission.
 */
export async function pickImage(opts: PickImageOptions = {}): Promise<File> {
  if (isNativePlatform()) {
    return pickViaCapacitor(opts);
  }
  return pickViaWebInput(opts);
}

// --- Capacitor (native) path -----------------------------------------------

async function pickViaCapacitor(opts: PickImageOptions): Promise<File> {
  // Lazy import so a web-only build (without the @capacitor/camera dep
  // installed in the lockfile yet) doesn't fail at module-load time.
  // The dynamic import is only awaited when ``isNativePlatform()``
  // returned true, which is impossible on a plain web bundle anyway.
  // @ts-ignore — type may be unresolvable until ``pnpm install`` pulls in @capacitor/camera; runtime guarded by isNativePlatform()
  const cap = (await import('@capacitor/camera')) as typeof import('@capacitor/camera');
  const { Camera, CameraResultType, CameraSource: CapSource } = cap;

  // Translate our public ``CameraSource`` string union into the
  // Capacitor enum value via an explicit branch — gives TypeScript
  // exact-typed access to the enum members without needing a Record
  // generic that has to know about the (private) underlying enum
  // value type.
  const source =
    opts.source === 'camera'
      ? CapSource.Camera
      : opts.source === 'gallery'
        ? CapSource.Photos
        : CapSource.Prompt;

  const photo = await Camera.getPhoto({
    quality: opts.quality ?? 85,
    width: opts.maxDimension ?? 2048,
    height: opts.maxDimension ?? 2048,
    resultType: CameraResultType.Uri,
    source,
    correctOrientation: true,
    allowEditing: false,
  });

  if (!photo.webPath) {
    throw new Error('Camera returned no image path');
  }
  const blob = await fetch(photo.webPath).then((r) => r.blob());
  return new File(
    [blob],
    opts.filename ?? `scan-${Date.now()}.${photo.format ?? 'jpg'}`,
    { type: blob.type || 'image/jpeg' },
  );
}

// --- Plain-web fallback path -----------------------------------------------

function pickViaWebInput(opts: PickImageOptions): Promise<File> {
  return new Promise((resolve, reject) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/jpeg,image/png,image/webp';
    // ``capture="environment"`` is a polite hint to mobile browsers to
    // default to the back camera, but it's just a hint — desktop and
    // older browsers ignore it and show a normal picker. The native
    // path above is where reliable camera access lives.
    if (opts.source === 'camera') {
      input.setAttribute('capture', 'environment');
    }
    input.style.display = 'none';
    document.body.appendChild(input);

    let resolved = false;
    input.onchange = () => {
      resolved = true;
      const file = input.files?.[0];
      document.body.removeChild(input);
      if (file) {
        resolve(file);
      } else {
        reject(new Error('No file selected'));
      }
    };
    // If the user cancels the file dialog there's no DOM event we can
    // listen to; the file element just stays empty. Clean up on a
    // refocus heartbeat so the hidden input doesn't accumulate.
    setTimeout(() => {
      if (!resolved && input.isConnected) {
        document.body.removeChild(input);
        reject(new Error('File picker cancelled'));
      }
    }, 60_000);

    input.click();
  });
}
