import { Outlet, useLocation } from 'react-router-dom';
import BottomNav from './ui/BottomNav';
import { getAccessToken } from '@/lib/auth';

/**
 * Layout dispatcher.
 *
 * Three modes the layout switches between based on the current route +
 * auth state:
 *
 * 1. **Auth-flow** (``/``, ``/login``, ``/disclaimer``)
 *    Centered card on a soft surface. No bottom nav, no app bar.
 *    Pages own their own headers.
 *
 * 2. **Tab roots** (``/home``, ``/scan``, ``/history``, ``/chat``,
 *    ``/profile``)
 *    Bottom nav visible. Each page renders its own AppBar via the
 *    shared component so titles, back arrows, and trailing actions
 *    stay page-controlled.
 *
 * 3. **Detail / modal pages** (``/result/:id``, ``/notifications``,
 *    ``/settings``, ``/admin/*``)
 *    No bottom nav (replaced by an AppBar back arrow on the page).
 *    Page owns its full chrome.
 *
 * We don't render the AppBar here at all — every page composes its
 * own so titles stay co-located with the page that owns them. Keeps
 * the layout dumb and easy to reason about.
 */
const AUTH_FLOW_ROUTES = new Set(['/', '/login', '/disclaimer', '/onboarding']);
const TAB_ROOT_ROUTES = new Set([
  '/home',
  '/scan',
  '/history',
  '/chat',
  '/profile',
]);

export default function Layout() {
  const { pathname } = useLocation();
  const isAuthFlow = AUTH_FLOW_ROUTES.has(pathname);
  const isTabRoot = TAB_ROOT_ROUTES.has(pathname);
  const isAuthed = !!getAccessToken();

  if (isAuthFlow) {
    return (
      <div className="min-h-screen bg-ink-50">
        <Outlet />
      </div>
    );
  }

  return (
    <div className="relative min-h-screen bg-ink-50">
      <main className={isTabRoot && isAuthed ? 'app-main' : ''}>
        <Outlet />
      </main>
      {isTabRoot && isAuthed ? <BottomNav /> : null}
    </div>
  );
}
