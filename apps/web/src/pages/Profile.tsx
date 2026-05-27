import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Bell,
  ChevronRight,
  CircleHelp,
  Database,
  Globe,
  Info,
  Loader2,
  LogOut,
  MapPin,
  MessageSquare,
  Settings as SettingsIcon,
  ShieldCheck,
  Sprout,
  Star,
  User as UserIcon,
} from 'lucide-react';
import type { UserRead } from '@bal/types';
import { api } from '@/lib/api';
import {
  clearAuth,
  getUserId,
  setUserName as cacheUserName,
  useRequireAuth,
  useRole,
} from '@/lib/auth';
import AppBar from '@/components/ui/AppBar';

/**
 * Profile / account screen — accessed via the bottom-nav "Profile" tab.
 *
 * Sections:
 *   - Identity card (avatar derived from name/ID, member-since from
 *     the real ``add_date`` returned by the API)
 *   - "About you" — name, location, farm size, primary crops. Each
 *     row is tappable: opens a bottom sheet with one input field and
 *     Save/Cancel. PATCH /users/me on save, optimistic local update.
 *   - Settings — sub-nav rows linking to /settings
 *   - Support — help, contact, rate, about
 *   - Sign out (danger button)
 *   - Version footer
 *
 * Loading model: we hit ``/users/me`` once on mount. While the request
 * is in flight we render a faint shimmer on the data rows (skeleton),
 * which avoids the jarring "swap from placeholder to real" beat. On
 * fetch error we still render the page so settings/support/sign-out
 * remain reachable — the data rows just show a retry CTA.
 */
type EditableField = 'name' | 'location' | 'farm_size' | 'crops';

export default function Profile() {
  useRequireAuth();
  const { t, i18n } = useTranslation();
  const nav = useNavigate();
  const userId = getUserId();
  const role = useRole();

  const [user, setUser] = useState<UserRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editing, setEditing] = useState<EditableField | null>(null);

  const loadUser = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const me = await api.users.me();
      setUser(me);
      // Refresh the cached display name in case it was changed from
      // another device / browser since this one logged in.
      cacheUserName(me.user_name ?? null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Failed to load profile');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  function signOut() {
    clearAuth();
    nav('/login', { replace: true });
  }

  // Identity card derivations
  const displayName = user?.user_name?.trim() || userId || '—';
  const initial = (user?.user_name?.trim() || userId || '?').slice(0, 1).toUpperCase();
  const memberSince = useMemo(() => {
    if (!user?.add_date) return null;
    const d = new Date(user.add_date);
    if (Number.isNaN(d.getTime())) return null;
    return d.toLocaleDateString(i18n.resolvedLanguage ?? undefined, {
      month: 'short',
      year: 'numeric',
    });
  }, [user?.add_date, i18n.resolvedLanguage]);

  // Computed display values for the About-you rows.
  const locationValue = useMemo(() => {
    const parts = [user?.city, user?.state].filter(Boolean);
    return parts.length > 0 ? parts.join(', ') : null;
  }, [user?.city, user?.state]);

  async function saveField(payload: Partial<UserRead>): Promise<void> {
    // Optimistic update + rollback on failure. Keeps the sheet snappy
    // — UI updates the moment Save is tapped, even if the network is
    // slow. We re-fetch on error so the rollback is exact (vs. trying
    // to remember the pre-edit state).
    const prev = user;
    setUser({ ...(user as UserRead), ...payload });
    try {
      // The schema's UserUpdate accepts only a subset; cast is safe
      // because every key we send here is a UserUpdate field.
      const updated = await api.users.updateMe(payload as Record<string, string>);
      setUser(updated);
      // Mirror display-name edits into the cached value so the Home
      // greeting refreshes without waiting for the next sign-in. The
      // ``user_name in payload`` check avoids stomping the cached
      // value on unrelated edits (location, farm size, crops).
      if ('user_name' in payload) {
        cacheUserName(updated.user_name ?? null);
      }
      setEditing(null);
    } catch (err) {
      setUser(prev);
      // Re-throw so the sheet can render an inline error without
      // closing.
      throw err;
    }
  }

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
            <p className="truncate font-display text-base font-semibold text-ink-800">
              {loading ? <span className="skeleton inline-block h-4 w-32" /> : displayName}
            </p>
            <p className="text-xs text-ink-500">
              {role === 'admin' ? 'Admin' : 'Member'}
              {memberSince ? ` · ${t('profile.member_since', { date: memberSince })}` : null}
            </p>
          </div>
        </div>

        {/* About you */}
        <section className="mt-6">
          <h3 className="section-heading">{t('profile.about_section')}</h3>
          <div className="card divide-y divide-ink-100 p-0">
            <ProfileRow
              icon={<UserIcon className="h-4 w-4" />}
              label={t('profile.your_name')}
              value={user?.user_name?.trim() || null}
              placeholder={t('profile.your_name_placeholder')}
              loading={loading}
              onTap={() => setEditing('name')}
            />
            <ProfileRow
              icon={<MapPin className="h-4 w-4" />}
              label={t('profile.farm_location')}
              value={locationValue}
              placeholder={t('profile.farm_location_placeholder')}
              loading={loading}
              onTap={() => setEditing('location')}
            />
            <ProfileRow
              icon={<Sprout className="h-4 w-4" />}
              label={t('profile.farm_size')}
              value={user?.farm_size?.trim() || null}
              placeholder={t('profile.farm_size_placeholder')}
              loading={loading}
              onTap={() => setEditing('farm_size')}
            />
            <ProfileRow
              icon={<Sprout className="h-4 w-4" />}
              label={t('profile.farm_crops')}
              value={user?.default_crop_interest?.trim() || null}
              placeholder={t('profile.farm_crops_placeholder')}
              loading={loading}
              onTap={() => setEditing('crops')}
            />
          </div>
          {loadError ? (
            <button
              type="button"
              onClick={loadUser}
              className="mt-2 text-xs font-medium text-leaf-600 hover:text-leaf-700"
            >
              {t('profile.retry_load')}
            </button>
          ) : null}
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

      {editing ? (
        <EditSheet
          field={editing}
          user={user}
          onSave={saveField}
          onClose={() => setEditing(null)}
        />
      ) : null}
    </>
  );
}

/* ============================================================
   Row primitives
   ============================================================ */
function ProfileRow({
  icon,
  label,
  value,
  placeholder,
  loading,
  onTap,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | null;
  placeholder: string;
  loading: boolean;
  onTap: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onTap}
      className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-ink-50"
    >
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-leaf-100 text-leaf-700">
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-2xs uppercase tracking-wider text-ink-500">{label}</p>
        {loading ? (
          <span className="skeleton mt-1 inline-block h-4 w-24" />
        ) : (
          <p
            className={
              value
                ? 'truncate text-sm text-ink-800'
                : 'truncate text-sm italic text-ink-400'
            }
          >
            {value ?? placeholder}
          </p>
        )}
      </div>
      <ChevronRight className="h-4 w-4 shrink-0 text-ink-400" />
    </button>
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

/* ============================================================
   Edit bottom sheet
   ============================================================
   Slides up from the bottom; tap-backdrop to dismiss. Location is
   the only field that needs two inputs (city + state) — every other
   field gets a single input. We keep the sheet's internal layout
   uniform by branching on the ``field`` prop. */
function EditSheet({
  field,
  user,
  onSave,
  onClose,
}: {
  field: EditableField;
  user: UserRead | null;
  onSave: (payload: Partial<UserRead>) => Promise<void>;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Per-field local state. Initialised from the current user record.
  const [name, setName] = useState(user?.user_name ?? '');
  const [city, setCity] = useState(user?.city ?? '');
  const [stateField, setStateField] = useState(user?.state ?? '');
  const [farmSize, setFarmSize] = useState(user?.farm_size ?? '');
  const [crops, setCrops] = useState(user?.default_crop_interest ?? '');

  // Lock body scroll while sheet is open so background doesn't drift
  // when the soft keyboard pushes the layout on Android.
  useEffect(() => {
    const original = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = original;
    };
  }, []);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      let payload: Partial<UserRead>;
      switch (field) {
        case 'name':
          payload = { user_name: name.trim() || null };
          break;
        case 'location':
          payload = {
            city: city.trim() || null,
            state: stateField.trim() || null,
          };
          break;
        case 'farm_size':
          payload = { farm_size: farmSize.trim() || null };
          break;
        case 'crops':
          payload = { default_crop_interest: crops.trim() || null };
          break;
      }
      await onSave(payload);
      // onSave closes the sheet on success via setEditing(null) in the
      // parent — no extra step here.
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  }

  const title = {
    name: t('profile.edit_name_title'),
    location: t('profile.edit_location_title'),
    farm_size: t('profile.edit_farm_size_title'),
    crops: t('profile.edit_crops_title'),
  }[field];

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      {/* Backdrop */}
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        className="absolute inset-0 bg-ink-900/40 animate-fade-in"
      />

      {/* Sheet */}
      <div
        className="relative w-full max-w-md rounded-t-2xl bg-white shadow-elev animate-slide-up sm:rounded-2xl"
        role="dialog"
        aria-modal="true"
      >
        {/* Drag handle (visual only) */}
        <div className="flex justify-center pt-3 pb-1 sm:hidden">
          <span className="h-1 w-10 rounded-full bg-ink-200" />
        </div>

        <div className="px-5 pt-2 pb-5 pb-safe">
          <h2 className="font-display text-lg font-semibold text-ink-800">{title}</h2>

          <div className="mt-4 space-y-3">
            {field === 'name' ? (
              <div>
                <label className="label" htmlFor="edit-name">
                  {t('profile.your_name')}
                </label>
                <input
                  id="edit-name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={t('profile.your_name_placeholder')}
                  className="input-lg"
                  maxLength={100}
                  autoFocus
                />
              </div>
            ) : null}

            {field === 'location' ? (
              <>
                <div>
                  <label className="label" htmlFor="edit-city">
                    {t('onboarding.location_city')}
                  </label>
                  <input
                    id="edit-city"
                    type="text"
                    value={city}
                    onChange={(e) => setCity(e.target.value)}
                    placeholder={t('onboarding.location_city_ph')}
                    className="input-lg"
                    maxLength={100}
                    autoFocus
                  />
                </div>
                <div>
                  <label className="label" htmlFor="edit-state">
                    {t('onboarding.location_state')}
                  </label>
                  <input
                    id="edit-state"
                    type="text"
                    value={stateField}
                    onChange={(e) => setStateField(e.target.value)}
                    placeholder={t('onboarding.location_state_ph')}
                    className="input-lg"
                    maxLength={50}
                  />
                </div>
              </>
            ) : null}

            {field === 'farm_size' ? (
              <div>
                <label className="label" htmlFor="edit-farm-size">
                  {t('profile.farm_size')}
                </label>
                <input
                  id="edit-farm-size"
                  type="text"
                  value={farmSize}
                  onChange={(e) => setFarmSize(e.target.value)}
                  placeholder={t('onboarding.farm_size_ph')}
                  className="input-lg"
                  maxLength={50}
                  autoFocus
                />
              </div>
            ) : null}

            {field === 'crops' ? (
              <div>
                <label className="label" htmlFor="edit-crops">
                  {t('profile.farm_crops')}
                </label>
                <input
                  id="edit-crops"
                  type="text"
                  value={crops}
                  onChange={(e) => setCrops(e.target.value)}
                  placeholder={t('onboarding.farm_crops_ph')}
                  className="input-lg"
                  maxLength={100}
                  autoFocus
                />
                <p className="help-text">{t('onboarding.farm_crops_help')}</p>
              </div>
            ) : null}
          </div>

          {error ? (
            <div className="mt-4 rounded-lg border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger">
              {error}
            </div>
          ) : null}

          <div className="mt-5 flex gap-3">
            <button
              type="button"
              onClick={onClose}
              disabled={saving}
              className="btn-ghost btn-lg flex-1"
            >
              {t('common.cancel')}
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="btn-primary btn-lg flex-1"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {t('common.save')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
