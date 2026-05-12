import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { api } from '@/lib/api';
import { CONSENT_VERSION, rememberConsent, useRequireAuth } from '@/lib/auth';

export default function Disclaimer() {
  useRequireAuth({ requireConsent: false });
  const { t } = useTranslation();
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function accept() {
    setBusy(true);
    setError(null);
    try {
      await api.auth.acceptConsent({ consent_version: CONSENT_VERSION });
      rememberConsent();
      nav('/home');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to record consent');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mx-auto max-w-xl py-12">
      <div className="card space-y-4">
        <h2 className="text-2xl font-semibold text-leaf-700">{t('disclaimer.title')}</h2>
        <p className="text-sm text-soil-500">{t('disclaimer.body_ai')}</p>
        <p className="text-sm text-soil-500">{t('disclaimer.body_pii')}</p>
        <button type="button" onClick={accept} disabled={busy} className="btn-primary w-full">
          {busy ? '…' : t('disclaimer.accept')}
        </button>
        {error && <p className="text-sm text-red-600">{error}</p>}
      </div>
    </section>
  );
}
