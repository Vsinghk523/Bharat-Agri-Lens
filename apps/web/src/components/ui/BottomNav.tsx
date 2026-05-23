import { NavLink, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Home, MessageCircle, History as HistoryIcon, User, Camera } from 'lucide-react';

/**
 * Bottom navigation — 5 tabs with the Scan tab elevated as a FAB-style
 * button in the center. Pattern adopted from Material 3 NavigationBar
 * with a tweak for the prominent primary action.
 *
 * Only shown on authenticated, "rooted" routes. Detail / modal routes
 * (Result, Settings, Notifications) inherit AppBar back navigation
 * instead. The Layout decides when to mount this.
 */
interface Tab {
  to: string;
  icon: typeof Home;
  key: string;
  defaultLabel: string;
  primary?: boolean;
}

const TABS: readonly Tab[] = [
  { to: '/home', icon: Home, key: 'nav.home', defaultLabel: 'Home' },
  { to: '/history', icon: HistoryIcon, key: 'nav.history', defaultLabel: 'History' },
  { to: '/scan', icon: Camera, key: 'nav.scan', defaultLabel: 'Scan', primary: true },
  { to: '/chat', icon: MessageCircle, key: 'nav.chat', defaultLabel: 'Chat' },
  { to: '/profile', icon: User, key: 'nav.profile', defaultLabel: 'Profile' },
] as const;

export default function BottomNav() {
  const { t } = useTranslation();
  const location = useLocation();

  return (
    <nav
      role="navigation"
      aria-label="Primary"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-ink-100 bg-white pb-safe"
      style={{ height: 'calc(var(--bottom-nav-h) + var(--safe-bottom))' }}
    >
      <div className="mx-auto grid h-16 max-w-2xl grid-cols-5 items-center">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const active = location.pathname === tab.to;
          if (tab.primary) {
            return (
              <NavLink
                key={tab.to}
                to={tab.to}
                aria-label={t(tab.key, tab.defaultLabel) ?? tab.defaultLabel}
                className="-mt-6 mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-leaf-600 text-white shadow-fab transition-transform hover:bg-leaf-700 active:scale-95"
              >
                <Icon className="h-6 w-6" strokeWidth={2.25} />
              </NavLink>
            );
          }
          return (
            <NavLink
              key={tab.to}
              to={tab.to}
              aria-label={t(tab.key, tab.defaultLabel) ?? tab.defaultLabel}
              className={
                active
                  ? 'flex h-full flex-col items-center justify-center gap-0.5 text-leaf-700'
                  : 'flex h-full flex-col items-center justify-center gap-0.5 text-ink-500 transition-colors hover:text-ink-700'
              }
            >
              <Icon
                className={active ? 'h-5 w-5' : 'h-5 w-5'}
                strokeWidth={active ? 2.5 : 2}
              />
              <span className={active ? 'text-2xs font-semibold' : 'text-2xs'}>
                {t(tab.key, tab.defaultLabel)}
              </span>
            </NavLink>
          );
        })}
      </div>
    </nav>
  );
}
