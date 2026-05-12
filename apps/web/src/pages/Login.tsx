import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { api } from '@/lib/api';
import { setAuth, setRole } from '@/lib/auth';

type Channel = 'email' | 'whatsapp';

export default function Login() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const [searchParams] = useSearchParams();
  const sessionExpired = searchParams.get('session') === 'expired';
  const [channel, setChannel] = useState<Channel>('whatsapp');
  const [email, setEmail] = useState('');
  const [mobile, setMobile] = useState('');
  const [code, setCode] = useState('');
  const [step, setStep] = useState<'request' | 'verify'>('request');
  const [error, setError] = useState<string | null>(null);

  async function requestOtp() {
    setError(null);
    try {
      await api.auth.requestOtp(
        channel === 'email'
          ? { channel, email }
          : { channel, isd_code: '91', mobile_no: Number(mobile) },
      );
      setStep('verify');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed');
    }
  }

  async function verifyOtp() {
    setError(null);
    try {
      const res = await api.auth.verifyOtp(
        channel === 'email'
          ? { channel, email, code }
          : { channel, mobile_no: Number(mobile), code },
      );
      setAuth(res.access_token, res.refresh_token, res.user_id);
      // Cache the role so Layout / Admin route guard don't need an
      // extra round-trip on every render. Best-effort — non-fatal
      // if the call fails; users.role defaults to 'user' anyway.
      try {
        const me = await api.users.me();
        setRole(me.role);
      } catch {
        setRole('user');
      }
      nav('/disclaimer');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Verification failed');
    }
  }

  return (
    <section className="mx-auto max-w-md py-12">
      <div className="card space-y-4">
        <h2 className="text-2xl font-semibold text-leaf-700">{t('login.title')}</h2>
        {sessionExpired && (
          <div
            role="status"
            className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900"
          >
            {t('login.session_expired')}
          </div>
        )}
        <div className="flex gap-2 text-sm">
          <button
            type="button"
            onClick={() => setChannel('whatsapp')}
            className={channel === 'whatsapp' ? 'btn-primary' : 'btn-secondary'}
          >
            WhatsApp
          </button>
          <button
            type="button"
            onClick={() => setChannel('email')}
            className={channel === 'email' ? 'btn-primary' : 'btn-secondary'}
          >
            Email
          </button>
        </div>

        {step === 'request' ? (
          <>
            {channel === 'email' ? (
              <input
                type="email"
                placeholder={t('login.email_ph')}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded border px-3 py-2"
              />
            ) : (
              <input
                type="tel"
                placeholder={t('login.mobile_ph')}
                value={mobile}
                onChange={(e) => setMobile(e.target.value)}
                className="w-full rounded border px-3 py-2"
              />
            )}
            <button type="button" onClick={requestOtp} className="btn-primary w-full">
              {t('login.send_otp')}
            </button>
          </>
        ) : (
          <>
            <input
              type="text"
              inputMode="numeric"
              placeholder={t('login.code_ph')}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="w-full rounded border px-3 py-2 tracking-widest"
            />
            <button type="button" onClick={verifyOtp} className="btn-primary w-full">
              {t('login.verify')}
            </button>
          </>
        )}

        {error && <p className="text-sm text-red-600">{error}</p>}
      </div>
    </section>
  );
}
