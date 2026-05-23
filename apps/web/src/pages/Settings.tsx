import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useRequireAuth, getUserId } from '@/lib/auth';
import AppBar from '@/components/ui/AppBar';
import LanguageSelector from '@/components/LanguageSelector';

/**
 * Settings — a flat scrolling page with toggles + read-only account
 * info. Toggle state is local for v0 (no /preferences API yet); when
 * we add server-side prefs we swap useState for a query/mutation.
 */
export default function Settings() {
  useRequireAuth();
  const { t } = useTranslation();
  const userId = getUserId();

  const [notifDiag, setNotifDiag] = useState(true);
  const [notifWeather, setNotifWeather] = useState(true);
  const [notifArticles, setNotifArticles] = useState(false);
  const [shareAnonData, setShareAnonData] = useState(true);

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
              checked={notifDiag}
              onChange={setNotifDiag}
            />
            <ToggleRow
              label={t('settings.notifications_weather')}
              hint={t('settings.notifications_weather_hint')}
              checked={notifWeather}
              onChange={setNotifWeather}
            />
            <ToggleRow
              label={t('settings.notifications_articles')}
              hint={t('settings.notifications_articles_hint')}
              checked={notifArticles}
              onChange={setNotifArticles}
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
              checked={shareAnonData}
              onChange={setShareAnonData}
              naked
            />
          </div>
        </section>

        {/* Account */}
        <section className="mb-6">
          <h3 className="section-heading">{t('settings.account_title')}</h3>
          <div className="card divide-y divide-ink-100 p-0">
            <ReadRow label={t('settings.account_email')} value="—" />
            <ReadRow label={t('settings.account_phone')} value="—" />
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
  onChange,
  naked,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  naked?: boolean;
}) {
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
      <span
        className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${
          checked ? 'bg-leaf-600' : 'bg-ink-200'
        }`}
      >
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          className="sr-only"
        />
        <span
          className={`inline-block h-5 w-5 rounded-full bg-white shadow-card transition-transform ${
            checked ? 'translate-x-5' : 'translate-x-0.5'
          }`}
        />
      </span>
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
