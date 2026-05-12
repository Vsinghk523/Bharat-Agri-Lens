import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

const ACCESS_KEY = 'bal_access_token';
const REFRESH_KEY = 'bal_refresh_token';
const USER_ID_KEY = 'bal_user_id';
const CONSENT_KEY = 'bal_consent_v1';

export const CONSENT_VERSION = 'v1';

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY);
}

export function getUserId(): string | null {
  return localStorage.getItem(USER_ID_KEY);
}

export function hasAcceptedConsent(): boolean {
  return localStorage.getItem(CONSENT_KEY) === CONSENT_VERSION;
}

export function setAuth(access: string, refresh: string, userId: string): void {
  localStorage.setItem(ACCESS_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
  localStorage.setItem(USER_ID_KEY, userId);
}

export function clearAuth(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(USER_ID_KEY);
  localStorage.removeItem(CONSENT_KEY);
}

export function rememberConsent(): void {
  localStorage.setItem(CONSENT_KEY, CONSENT_VERSION);
}

/** Redirect to /login if no token; redirect to /disclaimer if no consent. */
export function useRequireAuth(opts: { requireConsent?: boolean } = {}): void {
  const nav = useNavigate();
  const requireConsent = opts.requireConsent ?? true;
  useEffect(() => {
    if (!getAccessToken()) {
      nav('/login', { replace: true });
      return;
    }
    if (requireConsent && !hasAcceptedConsent()) {
      nav('/disclaimer', { replace: true });
    }
  }, [nav, requireConsent]);
}
