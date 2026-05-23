import type { CapacitorConfig } from '@capacitor/cli';

/**
 * Capacitor configuration for the BharatAgriLens mobile shell.
 *
 * ``webDir`` points at the built web app (apps/web/dist) — Capacitor
 * copies those static assets into both the Android and iOS native
 * projects at build time, so the mobile bundle ships with the exact
 * same React app the Railway-hosted web URL serves.
 *
 * ``server.androidScheme = 'https'`` makes the in-app WebView treat the
 * bundled assets as if they were loaded from an https origin. That
 * matters because: (a) CORS for the api calls works the same as on web
 * (your CORS_ALLOWED_ORIGINS on the api accepts the SPA origin), and
 * (b) APIs that require a secure context (camera permissions, service
 * workers, etc.) are happy.
 *
 * ``server.url`` is intentionally NOT set — if you ever want to test
 * a live-reload dev server pointing at your local Vite ``npm run dev``,
 * uncomment it and point at ``http://<your-laptop-LAN-IP>:5173``. For
 * release builds keep it commented so the bundled assets are used.
 */
const config: CapacitorConfig = {
  appId: 'in.bharatagrilens.app',
  appName: 'BharatAgriLens',
  webDir: '../web/dist',
  // server: {
  //   url: 'http://192.168.X.X:5173',  // your laptop's LAN IP for live reload
  //   cleartext: true,
  // },
  plugins: {
    Camera: {
      // Permission descriptions surface in the iOS permission prompt
      // and the Android manifest. Keep these in plain English; the
      // SPA's i18n bundle handles user-facing strings inside the app.
      permissions: {
        camera: 'Used to capture a photo of the plant for diagnosis.',
        photos: 'Used to pick an existing photo of the plant from your gallery.',
      },
    },
  },
  android: {
    // Allow http (cleartext) for local dev only. Production builds talk
    // to https://api-production-...up.railway.app which is TLS-protected
    // anyway; this just makes the local-LAN dev workflow above work.
    allowMixedContent: true,
  },
  ios: {
    // Capacitor needs a content inset behaviour declared so the safe
    // area (the home-indicator strip / notch) renders correctly with
    // our top-of-screen nav bar.
    contentInset: 'automatic',
  },
};

export default config;
