import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

const ACCESS_KEY = 'bal_access_token';
const REFRESH_KEY = 'bal_refresh_token';
const USER_ID_KEY = 'bal_user_id';
const ROLE_KEY = 'bal_user_role';
const CONSENT_KEY = 'bal_consent_v1';

export const CONSENT_VERSION = 'v1';

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY);
}

export function getUserId(): string | null {
  return localStorage.getItem(USER_ID_KEY);
}

export function getRole(): string | null {
  return localStorage.getItem(ROLE_KEY);
}

export function setRole(role: string): void {
  localStorage.setItem(ROLE_KEY, role);
}

export function isAdmin(): boolean {
  return getRole() === 'admin';
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
  localStorage.removeItem(ROLE_KEY);
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

/**
 * Like useRequireAuth, but also redirects to /home when the cached
 * role isn't 'admin'. Pairs with the server-side admin gate so a
 * non-admin user who somehow lands on /admin/* gets bounced before
 * any API call returns 403.
 */
export function useRequireAdmin(): void {
  useRequireAuth();
  const nav = useNavigate();
  useEffect(() => {
    if (!isAdmin()) nav('/home', { replace: true });
  }, [nav]);
}

/** React state mirror of getRole() that updates on storage events. */
export function useRole(): string | null {
  const [role, setRoleState] = useState<string | null>(getRole());
  useEffect(() => {
    function onStorage(e: StorageEvent) {
      if (e.key === ROLE_KEY) setRoleState(e.newValue);
    }
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);
  return role;
}
