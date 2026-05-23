import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Bell,
  ChevronRight,
  CircleHelp,
  Database,
  Globe,
  Info,
  LogOut,
  MapPin,
  MessageSquare,
  Settings as SettingsIcon,
  ShieldCheck,
  Sprout,
  Star,
} from 'lucide-react';
import { clearAuth, getUserId, useRequireAuth, useRole } from '@/lib/auth';
import AppBar from '@/components/ui/AppBar';

/**
 * Profile / account screen — accessed via the bottom-nav "Profile" tab.
 *
 * Sections:
 *   - User identity card (avatar, ID, member-since)
 *   - "My farm" — placeholder rows (location, size, primary crops).
 *     Edit flows can be wired later; UI surface is here so future
 *     iterations don't need a navigation redesign.
 *   - Settings — sub-nav rows linking to /settings (or future deep pages)
 *   - Support — help, contact, rate, about
 *   - Sign out (danger button)
 *   - Version footer
 */
export default function Profile() {
  useRequireAuth();
  const { t } = useTranslation();
  const nav = useNavigate();
  const userId = getUserId();
  const role = useRole();

  function signOut() {
    clearAuth();
    nav('/login', { replace: true });
  }

  const initial = (userId ?? '?').slice(0, 1).toUpperCase();

  return (
    <>
      <AppBar title={t('profile.title')} />

      <div className="mx-auto max-w-2xl px-4 py-5 animate-fade-in">
        {/* Identity card */}
        <div className="card flex items-center gap-4">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-leaf-500 to-leaf-700 font-display text-xl font-semibold text-white">
            {initial}
          </div>
          <div className="min-w-0 flex-1">
            <p className="font-display text-base font-semibold text-ink-800">
              {userId ?? '—'}
            </p>
            <p className="text-xs text-ink-500">
              {role === 'admin' ? 'Admin' : 'Member'} ·{' '}
              {t('profile.member_since', {
                date: new Date().toLocaleDateString(undefined, {
                  month: 'short',
                  year: 'numeric',
                }),
              })}
            </p>
          </div>
        </div>

        {/* My farm */}
        <section className="mt-6">
          <h3 className="section-heading">{t('profile.farm_section')}</h3>
          <div className="card divide-y divide-ink-100 p-0">
            <FarmRow
              icon={<MapPin className="h-4 w-4" />}
              label={t('profile.farm_location')}
              value={t('profile.farm_location_placeholder')}
              placeholder
            />
            <FarmRow
              icon={<Sprout className="h-4 w-4" />}
              label={t('profile.farm_size')}
              value={t('profile.farm_size_placeholder')}
              placeholder
            />
            <FarmRow
              icon={<Sprout className="h-4 w-4" />}
              label={t('profile.farm_crops')}
              value={t('profile.farm_crops_placeholder')}
              placeholder
            />
          </div>
        </section>

        {/* Settings */}
        <section className="mt-6">
          <h3 className="section-heading">{t('profile.settings_section')}</h3>
          <div className="card divide-y divide-ink-100 p-0">
            <SettingsRow
              icon={<Globe className="h-4 w-4" />}
              label={t('profile.settings_language')}
              to="/settings"
            />
            <SettingsRow
              icon={<Bell className="h-4 w-4" />}
              label={t('profile.settings_notifications')}
              hint={t('profile.settings_notifications_on')}
              to="/settings"
            />
            <SettingsRow
              icon={<MapPin className="h-4 w-4" />}
              label={t('profile.settings_location')}
              to="/settings"
            />
            <SettingsRow
              icon={<ShieldCheck className="h-4 w-4" />}
              label={t('profile.settings_privacy')}
              to="/settings"
            />
            <SettingsRow
              icon={<Database className="h-4 w-4" />}
              label={t('profile.settings_storage')}
              to="/settings"
            />
            <SettingsRow
              icon={<SettingsIcon className="h-4 w-4" />}
              label={t('nav.settings')}
              to="/settings"
            />
          </div>
        </section>

        {/* Support */}
        <section className="mt-6">
          <h3 className="section-heading">{t('profile.support_section')}</h3>
          <div className="card divide-y divide-ink-100 p-0">
            <SettingsRow
              icon={<CircleHelp className="h-4 w-4" />}
              label={t('profile.support_help')}
            />
            <SettingsRow
              icon={<MessageSquare className="h-4 w-4" />}
              label={t('profile.support_contact')}
            />
            <SettingsRow
              icon={<Star className="h-4 w-4" />}
              label={t('profile.support_rate')}
            />
            <SettingsRow
              icon={<Info className="h-4 w-4" />}
              label={t('profile.support_about')}
            />
          </div>
        </section>

        {/* Sign out */}
        <button
          type="button"
          onClick={signOut}
          className="btn-danger mt-6 w-full"
        >
          <LogOut className="h-4 w-4" />
          {t('profile.signout')}
        </button>

        <p className="mt-4 text-center text-xs text-ink-400">
          {t('profile.version', { version: '0.1.0' })}
        </p>
        <p className="mt-1 text-center text-xs text-ink-400">
          {t('profile.footer_made')}
        </p>
      </div>
    </>
  );
}

function FarmRow({
  icon,
  label,
  value,
  placeholder,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  placeholder?: boolean;
}) {
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-leaf-100 text-leaf-700">
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-2xs uppercase tracking-wider text-ink-500">{label}</p>
        <p
          className={
            placeholder
              ? 'truncate text-sm italic text-ink-400'
              : 'truncate text-sm text-ink-800'
          }
        >
          {value}
        </p>
      </div>
    </div>
  );
}

function SettingsRow({
  icon,
  label,
  hint,
  to,
}: {
  icon: React.ReactNode;
  label: string;
  hint?: string;
  to?: string;
}) {
  const body = (
    <div className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-ink-50">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-ink-100 text-ink-700">
        {icon}
      </span>
      <span className="min-w-0 flex-1 truncate text-sm text-ink-800">{label}</span>
      {hint ? <span className="text-xs text-ink-500">{hint}</span> : null}
      <ChevronRight className="h-4 w-4 shrink-0 text-ink-400" />
    </div>
  );
  return to ? <Link to={to}>{body}</Link> : <button type="button" className="w-full">{body}</button>;
}
