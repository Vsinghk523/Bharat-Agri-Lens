import { createApiClient } from '@bal/api-client';
import { clearAuth, getAccessToken } from './auth';

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? '/api';

// Module-level guard so concurrent 401s don't kick off multiple redirects.
let redirecting = false;

export const api = createApiClient({
  baseUrl,
  getAccessToken,
  onUnauthorized: () => {
    if (redirecting) return;
    redirecting = true;
    clearAuth();
    // Avoid a redirect loop if we're already on /login. Tag the URL so
    // Login.tsx can show a "session expired" banner.
    if (window.location.pathname !== '/login') {
      window.location.assign('/login?session=expired');
    }
  },
});
