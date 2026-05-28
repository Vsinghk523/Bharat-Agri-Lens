/**
 * Push-notification registration shim.
 *
 * Plain web builds: we don't have FCM at all (web push via VAPID is a
 * separate workstream), so ``initializePush`` is a no-op. The function
 * exists at the module's top level so callers don't need to guard
 * with ``isNativePlatform()``.
 *
 * Android / iOS (Capacitor): we lazily import @capacitor/push-notifications,
 * request the OS permission, wait for FCM to hand us a registration
 * token, and POST it to our backend (``/push/register-token``). On
 * success we also stash the token in localStorage so a future sign-out
 * can pass it to the unregister endpoint.
 *
 * Listeners attached:
 *   - ``registration``       → POST token to backend
 *   - ``registrationError``  → log only (FCM rotates infrequently;
 *                              user can sign-out+in to retry)
 *   - ``pushNotificationReceived`` → render a brief toast (TODO: hook
 *                              to a real toast component once we have
 *                              one); for now we just log
 *   - ``pushNotificationActionPerformed`` → deeplink based on the
 *                              ``data.type`` field set by the backend.
 *                              Today's types: ``diagnosis_reviewed``,
 *                              ``daily_tip``.
 *
 * Idempotency: ``initializePush`` records that it ran via a module-
 * level flag, so multiple calls (e.g. on every page render) only
 * fire FCM register once per app launch.
 */
import { api } from './api';
import { getAccessToken } from './auth';
import { getPlatform, isNativePlatform } from './platform';

const TOKEN_LS_KEY = 'bal_fcm_token';

let initialized = false;
let pendingDeeplink: ((path: string) => void) | null = null;

/**
 * Register a deeplink handler that will be called when a notification
 * is tapped and we've decoded a target path. Wired in App.tsx with
 * react-router's navigate.
 */
export function setPushDeeplinkHandler(handler: (path: string) => void): void {
  pendingDeeplink = handler;
}

export async function initializePush(): Promise<void> {
  if (initialized) return;
  initialized = true;

  if (!isNativePlatform()) {
    // Web build: nothing to do. Web push (VAPID) is a future workstream.
    return;
  }
  if (!getAccessToken()) {
    // Need an authed user to register the token. Caller should
    // re-invoke after a successful login.
    initialized = false;
    return;
  }

  const platform = getPlatform();
  if (platform !== 'android' && platform !== 'ios') return;

  let PushNotifications: typeof import('@capacitor/push-notifications').PushNotifications;
  try {
    ({ PushNotifications } = await import('@capacitor/push-notifications'));
  } catch (err) {
    console.warn('push: plugin import failed', err);
    return;
  }

  // Request OS-level permission. On Android 13+ this triggers the
  // POST_NOTIFICATIONS runtime prompt; on Android 12 and below it's a
  // no-op return of 'granted'.
  const perm = await PushNotifications.requestPermissions();
  if (perm.receive !== 'granted') {
    console.info('push: permission not granted, skipping registration');
    return;
  }

  // Wire listeners BEFORE register() — the registration event can
  // fire synchronously on Android with a cached token.
  PushNotifications.addListener('registration', async (token) => {
    try {
      await api.push.registerToken({
        token: token.value,
        platform: platform as 'android' | 'ios',
      });
      localStorage.setItem(TOKEN_LS_KEY, token.value);
    } catch (err) {
      console.warn('push: register-token API call failed', err);
    }
  });

  PushNotifications.addListener('registrationError', (err) => {
    console.warn('push: FCM registration error', err);
  });

  PushNotifications.addListener('pushNotificationReceived', (notification) => {
    // Foreground notification — payload received but the OS didn't
    // tray it (the app is open). Log for now; a follow-up will hook
    // a transient in-app toast.
    console.info('push: received', notification);
  });

  PushNotifications.addListener('pushNotificationActionPerformed', (action) => {
    const data = (action.notification.data ?? {}) as Record<string, string>;
    const type = data.type;
    let path: string | null = null;
    if (type === 'diagnosis_reviewed' && data.diagnostic_id) {
      path = `/result/${data.diagnostic_id}`;
    } else if (type === 'daily_tip') {
      path = '/home';
    }
    if (path && pendingDeeplink) {
      pendingDeeplink(path);
    }
  });

  await PushNotifications.register();
}

/**
 * Sign-out helper. Calls the unregister endpoint for the cached token
 * (best-effort), then clears local state. Called from clearAuth().
 */
export async function unregisterPush(): Promise<void> {
  const token = localStorage.getItem(TOKEN_LS_KEY);
  if (!token) return;
  try {
    await api.push.unregisterToken(token);
  } catch (err) {
    console.warn('push: unregister API call failed', err);
  }
  localStorage.removeItem(TOKEN_LS_KEY);
  initialized = false;
}
