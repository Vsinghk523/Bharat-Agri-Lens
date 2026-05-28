import { useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, ArrowRight, Leaf, Loader2, Mail, MessageSquare } from 'lucide-react';
import { api } from '@/lib/api';
import { markOnboardingComplete, setAuth, setRole, setUserName } from '@/lib/auth';
import { initializePush } from '@/lib/push';

type Channel = 'email' | 'whatsapp';

/**
 * Login — single screen, two steps.
 *
 * Step 1: choose channel (WhatsApp / Email), enter contact, send code.
 * Step 2: enter 6-digit code, verify, set auth tokens, route to disclaimer.
 *
 * Channel tabs render as a segmented control. Inputs get the new
 * ``.input`` style with leading icon. Errors render in-line as a
 * danger-tinted alert below the active CTA.
 */
export default function Login() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const [searchParams] = useSearchParams();
  const sessionExpired = searchParams.get('session') === 'expired';

  const [channel, setChannel] = useState<Channel>('email');
  const [email, setEmail] = useState('');
  const [mobile, setMobile] = useState('');
  const [code, setCode] = useState('');
  const [step, setStep] = useState<'request' | 'verify'>('request');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const target = channel === 'email' ? email : `+91 ${mobile}`;

  async function requestOtp() {
    setError(null);
    setBusy(true);
    try {
      await api.auth.requestOtp(
        channel === 'email'
          ? { channel, email }
          : { channel, isd_code: '91', mobile_no: Number(mobile) },
      );
      setStep('verify');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed');
    } finally {
      setBusy(false);
    }
  }

  async function verifyOtp() {
    setError(null);
    setBusy(true);
    try {
      const res = await api.auth.verifyOtp(
        channel === 'email'
          ? { channel, email, code }
          : { channel, mobile_no: Number(mobile), code },
      );
      setAuth(res.access_token, res.refresh_token, res.user_id);
      try {
        const me = await api.users.me();
        setRole(me.role);
        // Hydrate the cached display name so Home can greet the user
        // by name on the next render — no extra round-trip needed.
        setUserName(me.user_name);
        // If the user already has *any* onboarding-collected data
        // (city / state / farm size / primary crops), skip the wizard
        // on this device. This is what makes returning users on a new
        // install go straight to /home after consent instead of being
        // re-walked through the 4-step onboarding they already did.
        const hasOnboardingData = Boolean(
          me.city || me.state || me.farm_size || me.default_crop_interest,
        );
        if (hasOnboardingData) {
          markOnboardingComplete();
        }
      } catch {
        setRole('user');
      }
      // Fire-and-forget — push registration shouldn't gate the
      // disclaimer redirect. No-op on web.
      initializePush().catch(() => {});
      nav('/disclaimer');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Verification failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-main animate-fade-in">
      {/* Brand */}
      <Link to="/" className="mb-8 flex items-center gap-2">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-leaf-600 text-white shadow-card">
          <Leaf className="h-5 w-5" strokeWidth={2.25} />
        </span>
        <span className="font-display text-lg font-semibold text-ink-800">
          BharatAgriLens
        </span>
      </Link>

      <div className="card w-full">
        {step === 'request' ? (
          <>
            <h1 className="font-display text-2xl font-semibold text-ink-800">
              {t('login.title')}
            </h1>
            <p className="mt-1 text-sm text-ink-500">{t('login.subtitle')}</p>

            {sessionExpired ? (
              <div
                role="status"
                className="mt-3 rounded-lg border border-saffron-300 bg-saffron-50 px-3 py-2 text-sm text-saffron-700"
              >
                {t('login.session_expired')}
              </div>
            ) : null}

            {/* Segmented channel selector */}
            <div className="mt-5 grid grid-cols-2 gap-1 rounded-lg bg-ink-100 p-1">
              <button
                type="button"
                onClick={() => setChannel('email')}
                className={
                  channel === 'email'
                    ? 'inline-flex items-center justify-center gap-1.5 rounded-md bg-white px-3 py-1.5 text-sm font-semibold text-leaf-700 shadow-card'
                    : 'inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-ink-600'
                }
              >
                <Mail className="h-4 w-4" />
                {t('login.tab_email')}
              </button>
              <button
                type="button"
                onClick={() => setChannel('whatsapp')}
                className={
                  channel === 'whatsapp'
                    ? 'inline-flex items-center justify-center gap-1.5 rounded-md bg-white px-3 py-1.5 text-sm font-semibold text-leaf-700 shadow-card'
                    : 'inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-ink-600'
                }
              >
                <MessageSquare className="h-4 w-4" />
                {t('login.tab_whatsapp')}
              </button>
            </div>

            <div className="mt-4 space-y-3">
              {channel === 'email' ? (
                <input
                  type="email"
                  autoComplete="email"
                  inputMode="email"
                  placeholder={t('login.email_ph')}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="input-lg"
                />
              ) : (
                <input
                  type="tel"
                  autoComplete="tel-national"
                  inputMode="numeric"
                  placeholder={t('login.mobile_ph')}
                  value={mobile}
                  onChange={(e) => setMobile(e.target.value)}
                  className="input-lg"
                />
              )}

              <button
                type="button"
                onClick={requestOtp}
                disabled={busy || (channel === 'email' ? !email : !mobile)}
                className="btn-primary btn-lg w-full"
              >
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {t('login.send_otp')}
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </>
        ) : (
          <>
            <button
              type="button"
              onClick={() => {
                setStep('request');
                setCode('');
                setError(null);
              }}
              className="-ml-1 mb-3 inline-flex items-center gap-1 text-sm text-ink-500 hover:text-ink-700"
            >
              <ArrowLeft className="h-4 w-4" />
              {t('common.back')}
            </button>

            <h1 className="font-display text-2xl font-semibold text-ink-800">
              {t('login.verify')}
            </h1>
            <p className="mt-1 text-sm text-ink-500">
              {t('login.code_sent_to', { target })}
            </p>

            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              placeholder={t('login.code_ph')}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
              className="input-lg mt-5 text-center text-2xl font-semibold tracking-[0.4em]"
            />

            <button
              type="button"
              onClick={verifyOtp}
              disabled={busy || code.length < 4}
              className="btn-primary btn-lg mt-4 w-full"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {t('login.verify')}
            </button>

            <button
              type="button"
              onClick={requestOtp}
              disabled={busy}
              className="btn-ghost mt-2 w-full text-xs"
            >
              {t('login.resend')}
            </button>
          </>
        )}

        {error ? (
          <div className="mt-4 rounded-lg border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger">
            {error}
          </div>
        ) : null}
      </div>

      <p className="mt-6 px-6 text-center text-xs text-ink-500">
        {t('footer.tagline')}
      </p>
    </div>
  );
}
