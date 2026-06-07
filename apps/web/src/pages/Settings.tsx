import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';
import type { UserPreferences, UserRead } from '@bal/types';
import { api } from '@/lib/api';
import { useRequireAuth, getUserId } from '@/lib/auth';
import AppBar from '@/components/ui/AppBar';
import LanguageSelector from '@/components/LanguageSelector';

/**
 * Settings — flat scrolling page with notification + privacy toggles
 * and read-only account info.
 *
 * Toggle state lives server-side under ``users.preferences`` (a JSONB
 * column). The page fetches ``/users/me`` once on mount to hydrate the
 * toggles; every flip fires an optimistic ``PATCH /users/me/preferences``
 * with rollback on failure.
 *
 * The Account section renders real ``user_email`` + formatted
 * ``mobile_no`` from the same fetch — they used to be hardcoded em-
 * dashes which made the section look broken.
 */
export default function Settings() {
  useRequireAuth();
  const { t } = useTranslation();
  const userId = getUserId();

  const [user, setUser] = useState<UserRead | null>(null);
  const [prefs, setPrefs] = useState<UserPreferences | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<keyof UserPreferences | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadUser = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const me = await api.users.me();
      setUser(me);
      setPrefs(me.preferences);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load settings');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  async function togglePref(key: keyof UserPreferences, next: boolean) {
    if (!prefs) return;
    // Optimistic flip — UI feels instant even on slow networks.
    const prev = prefs;
    setPrefs({ ...prefs, [key]: next });
    setSaving(key);
    setError(null);
    try {
      const updated = await api.users.updateMyPreferences({ [key]: next });
      setPrefs(updated);
    } catch (err) {
      // Roll back on failure and surface a banner.
      setPrefs(prev);
      setError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setSaving(null);
    }
  }

  // Formatted account display.
  const emailDisplay = user?.user_email || '—';
  const phoneDisplay =
    user?.mobile_no && user?.isd_code
      ? `+${user.isd_code} ${user.mobile_no}`
      : user?.mobile_no
        ? String(user.mobile_no)
        : '—';

  return (
    <>
      <AppBar showBack title={t('settings.title')} />

      <div className="mx-auto max-w-2xl px-4 py-5 animate-fade-in">
        {/* Language */}
        <section className="mb-6">
          <h3 className="section-heading">{t('profile.settings_language')}</h3>
          <div className="card">
            <LanguageSelector variant="full" />
          </div>
        </section>

        {/* Notifications */}
        <section className="mb-6">
          <h3 className="section-heading">{t('settings.notifications_title')}</h3>
          <div className="card divide-y divide-ink-100 p-0">
            <ToggleRow
              label={t('settings.notifications_diagnoses')}
              hint={t('settings.notifications_diagnoses_hint')}
              checked={prefs?.notif_diagnoses ?? true}
              loading={loading}
              saving={saving === 'notif_diagnoses'}
              onChange={(v) => togglePref('notif_diagnoses', v)}
            />
            <ToggleRow
              label={t('settings.notifications_weather')}
              hint={t('settings.notifications_weather_hint')}
              checked={prefs?.notif_weather ?? true}
              loading={loading}
              saving={saving === 'notif_weather'}
              onChange={(v) => togglePref('notif_weather', v)}
            />
            <ToggleRow
              label={t('settings.notifications_treatment_reminders')}
              hint={t('settings.notifications_treatment_reminders_hint')}
              checked={prefs?.notif_treatment_reminders ?? true}
              loading={loading}
              saving={saving === 'notif_treatment_reminders'}
              onChange={(v) => togglePref('notif_treatment_reminders', v)}
            />
            <ToggleRow
              label={t('settings.notifications_outbreak_alerts')}
              hint={t('settings.notifications_outbreak_alerts_hint')}
              checked={prefs?.notif_outbreak_alerts ?? true}
              loading={loading}
              saving={saving === 'notif_outbreak_alerts'}
              onChange={(v) => togglePref('notif_outbreak_alerts', v)}
            />
            <ToggleRow
              label={t('settings.notifications_daily_tip')}
              hint={t('settings.notifications_daily_tip_hint')}
              checked={prefs?.notif_daily_tip ?? false}
              loading={loading}
              saving={saving === 'notif_daily_tip'}
              onChange={(v) => togglePref('notif_daily_tip', v)}
            />
            <ToggleRow
              label={t('settings.notifications_articles')}
              hint={t('settings.notifications_articles_hint')}
              checked={prefs?.notif_articles ?? false}
              loading={loading}
              saving={saving === 'notif_articles'}
              onChange={(v) => togglePref('notif_articles', v)}
            />
          </div>
        </section>

        {/* Privacy */}
        <section className="mb-6">
          <h3 className="section-heading">{t('settings.privacy_title')}</h3>
          <div className="card">
            <ToggleRow
              label={t('settings.privacy_share_data')}
              hint={t('settings.privacy_share_data_hint')}
              checked={prefs?.privacy_share_anonymous_data ?? true}
              loading={loading}
              saving={saving === 'privacy_share_anonymous_data'}
              onChange={(v) => togglePref('privacy_share_anonymous_data', v)}
              naked
            />
          </div>
        </section>

        {error ? (
          <div className="mb-4 rounded-lg border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger">
            {error}
          </div>
        ) : null}

        {/* Account */}
        <section className="mb-6">
          <h3 className="section-heading">{t('settings.account_title')}</h3>
          <div className="card divide-y divide-ink-100 p-0">
            <ReadRow
              label={t('settings.account_email')}
              value={loading ? '…' : emailDisplay}
            />
            <ReadRow
              label={t('settings.account_phone')}
              value={loading ? '…' : phoneDisplay}
            />
            <ReadRow label="User ID" value={userId ?? '—'} mono />
          </div>
        </section>

        {/* Danger zone */}
        <section>
          <button type="button" className="btn-danger w-full">
            {t('settings.account_delete')}
          </button>
          <p className="mt-2 px-2 text-center text-xs text-ink-500">
            {t('settings.account_delete_hint')}
          </p>
        </section>
      </div>
    </>
  );
}

function ToggleRow({
  label,
  hint,
  checked,
  loading,
  saving,
  onChange,
  naked,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  loading?: boolean;
  saving?: boolean;
  onChange: (v: boolean) => void;
  naked?: boolean;
}) {
  const disabled = !!loading || !!saving;
  return (
    <label
      className={
        naked
          ? 'flex cursor-pointer items-center justify-between gap-3'
          : 'flex cursor-pointer items-center justify-between gap-3 px-4 py-3 transition-colors hover:bg-ink-50'
      }
    >
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-ink-800">{label}</p>
        {hint ? <p className="mt-0.5 text-xs text-ink-500">{hint}</p> : null}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {saving ? <Loader2 className="h-3 w-3 animate-spin text-ink-400" /> : null}
        <span
          className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${
            disabled ? 'opacity-60' : ''
          } ${checked ? 'bg-leaf-600' : 'bg-ink-200'}`}
        >
          <input
            type="checkbox"
            checked={checked}
            disabled={disabled}
            onChange={(e) => onChange(e.target.checked)}
            className="sr-only"
          />
          <span
            className={`inline-block h-5 w-5 rounded-full bg-white shadow-card transition-transform ${
              checked ? 'translate-x-5' : 'translate-x-0.5'
            }`}
          />
        </span>
      </div>
    </label>
  );
}

function ReadRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3">
      <span className="text-sm text-ink-800">{label}</span>
      <span className={mono ? 'font-mono text-xs text-ink-500' : 'text-sm text-ink-500'}>
        {value}
      </span>
    </div>
  );
}
