import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { CircleAlert, Loader2, Lock, ShieldCheck } from 'lucide-react';
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
    <div className="auth-main animate-fade-in">
      <div className="mb-6 flex h-14 w-14 items-center justify-center rounded-2xl bg-leaf-100 text-leaf-700">
        <ShieldCheck className="h-7 w-7" />
      </div>

      <h1 className="font-display text-2xl font-semibold text-ink-800">
        {t('disclaimer.title')}
      </h1>

      <div className="mt-6 w-full space-y-3">
        <div className="card flex items-start gap-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-saffron-100 text-saffron-700">
            <CircleAlert className="h-4 w-4" />
          </span>
          <p className="text-sm leading-relaxed text-ink-700">
            {t('disclaimer.body_ai')}
          </p>
        </div>

        <div className="card flex items-start gap-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-leaf-100 text-leaf-700">
            <Lock className="h-4 w-4" />
          </span>
          <p className="text-sm leading-relaxed text-ink-700">
            {t('disclaimer.body_pii')}
          </p>
        </div>
      </div>

      <button
        type="button"
        onClick={accept}
        disabled={busy}
        className="btn-primary btn-lg mt-6 w-full"
      >
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
        {t('disclaimer.accept')}
      </button>

      {error ? (
        <div className="mt-4 w-full rounded-lg border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger">
          {error}
        </div>
      ) : null}
    </div>
  );
}
