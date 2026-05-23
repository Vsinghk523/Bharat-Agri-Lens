import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Leaf,
  Loader2,
  MapPin,
  Sprout,
} from 'lucide-react';
import { api } from '@/lib/api';
import {
  hasCompletedOnboarding,
  markOnboardingComplete,
  useRequireAuth,
} from '@/lib/auth';

/**
 * Onboarding — 4-step wizard shown after first-time sign-in + consent.
 *
 * The intent is to capture enough farm context up front that the rest
 * of the app (home dashboard, scan results, chat) can personalise
 * itself ("your tomatoes", "in your district"). Steps:
 *
 *   1. Welcome — brand intro, sets expectation that this takes ~30s.
 *   2. Location — city + state (district). We accept free text rather
 *      than locking to a dropdown because rural place names vary
 *      wildly and the cost of mismatched options is worse than the
 *      cost of accepting a typo.
 *   3. Farm — farm size + primary crops. Free text again; we don't
 *      want to make the farmer pick from "rice/wheat/cotton" when
 *      they grow turmeric.
 *   4. Done — confirmation + CTA to scan their first plant.
 *
 * The API call to ``api.users.updateMe`` happens once on the final
 * "Finish" tap — we batch the writes so a farmer who quits halfway
 * doesn't leave a half-filled row. The encrypted-at-rest story on
 * the backend (see ``app/common/encryption.py``) means even the
 * partial submission would be safe, but batching is still the right
 * UX: it lets the farmer reverse direction without server round-trips.
 *
 * After success we set a local-storage flag (``bal_onboarded``) so
 * useRequireAuth skips the redirect on subsequent sessions. We don't
 * use the server's user record as the source of truth here because
 * an existing user (re-installing the app on a new device) might
 * already have all the data — the flag tells us "we asked them, they
 * answered, move on" independent of whether the answers are saved.
 */

type Step = 0 | 1 | 2 | 3;

interface FormState {
  city: string;
  state: string;
  farmSize: string;
  crops: string;
}

export default function Onboarding() {
  // We're the page that records the "onboarded" flag, so don't gate
  // ourselves on it — that would cause a loop. Still require token +
  // consent though.
  useRequireAuth({ requireOnboarding: false });
  const { t } = useTranslation();
  const nav = useNavigate();
  const [step, setStep] = useState<Step>(0);
  const [form, setForm] = useState<FormState>({
    city: '',
    state: '',
    farmSize: '',
    crops: '',
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // If the farmer somehow lands here after already onboarding (deep
  // link from a notification, refresh, etc.) send them straight home.
  useEffect(() => {
    if (hasCompletedOnboarding()) nav('/home', { replace: true });
  }, [nav]);

  const progress = useMemo(() => ((step + 1) / 4) * 100, [step]);

  function update<K extends keyof FormState>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function next() {
    if (step < 3) setStep((step + 1) as Step);
  }

  function back() {
    if (step > 0) setStep((step - 1) as Step);
  }

  async function finish() {
    setBusy(true);
    setError(null);
    try {
      // Submit only fields the farmer actually filled. Empty strings
      // would write an encrypted empty value — fine technically, but
      // sending undefined keeps the column NULL which the rest of
      // the app already handles as "not set yet".
      const payload: Record<string, string> = {};
      if (form.city.trim()) payload.city = form.city.trim();
      if (form.state.trim()) payload.state = form.state.trim();
      if (form.farmSize.trim()) payload.farm_size = form.farmSize.trim();
      if (form.crops.trim()) payload.default_crop_interest = form.crops.trim();

      if (Object.keys(payload).length > 0) {
        await api.users.updateMe(payload);
      }
      markOnboardingComplete();
      nav('/home', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save profile');
    } finally {
      setBusy(false);
    }
  }

  // Validation per step. We're permissive — every field is optional
  // so the farmer can skip ahead if they want.
  const canAdvance = true;

  return (
    <div className="auth-main animate-fade-in">
      {/* Progress rail */}
      <div className="mb-6 w-full">
        <div className="mb-2 flex items-center justify-between text-2xs font-medium uppercase tracking-wider text-ink-500">
          <span>{t('onboarding.step_label', { current: step + 1, total: 4 })}</span>
          {step > 0 && step < 3 ? (
            <button
              type="button"
              onClick={finish}
              disabled={busy}
              className="text-leaf-600 hover:text-leaf-700"
            >
              {t('onboarding.skip')}
            </button>
          ) : null}
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink-100">
          <div
            className="h-full bg-leaf-500 transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {step === 0 ? <WelcomeStep /> : null}
      {step === 1 ? (
        <LocationStep form={form} update={update} />
      ) : null}
      {step === 2 ? <FarmStep form={form} update={update} /> : null}
      {step === 3 ? <DoneStep form={form} /> : null}

      {error ? (
        <div className="mt-4 w-full rounded-lg border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger">
          {error}
        </div>
      ) : null}

      {/* Footer nav */}
      <div className="mt-6 flex w-full items-center gap-3">
        {step > 0 ? (
          <button
            type="button"
            onClick={back}
            disabled={busy}
            className="btn-ghost btn-lg flex-1"
          >
            <ArrowLeft className="h-4 w-4" />
            {t('common.back')}
          </button>
        ) : null}

        {step < 3 ? (
          <button
            type="button"
            onClick={next}
            disabled={!canAdvance || busy}
            className="btn-primary btn-lg flex-1"
          >
            {step === 0 ? t('onboarding.cta_get_started') : t('onboarding.cta_next')}
            <ArrowRight className="h-4 w-4" />
          </button>
        ) : (
          <button
            type="button"
            onClick={finish}
            disabled={busy}
            className="btn-primary btn-lg flex-1"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {t('onboarding.cta_finish')}
          </button>
        )}
      </div>
    </div>
  );
}

/* ============================================================
   Step 0 — Welcome
   ============================================================ */
function WelcomeStep() {
  const { t } = useTranslation();
  return (
    <>
      <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-leaf-100 text-leaf-700">
        <Leaf className="h-8 w-8" />
      </div>
      <h1 className="text-center font-display text-2xl font-semibold text-ink-800">
        {t('onboarding.welcome_title')}
      </h1>
      <p className="mt-3 text-center text-sm leading-relaxed text-ink-600">
        {t('onboarding.welcome_subtitle')}
      </p>

      <div className="mt-6 w-full space-y-3">
        <div className="card flex items-start gap-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-leaf-100 text-leaf-700">
            <MapPin className="h-4 w-4" />
          </span>
          <div>
            <p className="text-sm font-medium text-ink-800">
              {t('onboarding.welcome_point_1_title')}
            </p>
            <p className="text-xs text-ink-600">
              {t('onboarding.welcome_point_1_body')}
            </p>
          </div>
        </div>

        <div className="card flex items-start gap-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-saffron-100 text-saffron-700">
            <Sprout className="h-4 w-4" />
          </span>
          <div>
            <p className="text-sm font-medium text-ink-800">
              {t('onboarding.welcome_point_2_title')}
            </p>
            <p className="text-xs text-ink-600">
              {t('onboarding.welcome_point_2_body')}
            </p>
          </div>
        </div>
      </div>

      <p className="mt-4 text-center text-xs text-ink-500">
        {t('onboarding.welcome_duration')}
      </p>
    </>
  );
}

/* ============================================================
   Step 1 — Location
   ============================================================ */
interface StepProps {
  form: FormState;
  update: <K extends keyof FormState>(key: K, value: string) => void;
}

function LocationStep({ form, update }: StepProps) {
  const { t } = useTranslation();
  return (
    <>
      <div className="mb-6 flex h-14 w-14 items-center justify-center rounded-2xl bg-leaf-100 text-leaf-700">
        <MapPin className="h-7 w-7" />
      </div>
      <h2 className="text-center font-display text-xl font-semibold text-ink-800">
        {t('onboarding.location_title')}
      </h2>
      <p className="mt-2 text-center text-sm text-ink-600">
        {t('onboarding.location_subtitle')}
      </p>

      <div className="mt-6 w-full space-y-4">
        <div>
          <label className="label" htmlFor="onb-city">
            {t('onboarding.location_city')}
          </label>
          <input
            id="onb-city"
            type="text"
            value={form.city}
            onChange={(e) => update('city', e.target.value)}
            placeholder={t('onboarding.location_city_ph')}
            className="input-lg"
            maxLength={100}
            autoComplete="address-level2"
          />
        </div>

        <div>
          <label className="label" htmlFor="onb-state">
            {t('onboarding.location_state')}
          </label>
          <input
            id="onb-state"
            type="text"
            value={form.state}
            onChange={(e) => update('state', e.target.value)}
            placeholder={t('onboarding.location_state_ph')}
            className="input-lg"
            maxLength={50}
            autoComplete="address-level1"
          />
          <p className="help-text">{t('onboarding.location_help')}</p>
        </div>
      </div>
    </>
  );
}

/* ============================================================
   Step 2 — Farm details
   ============================================================ */
function FarmStep({ form, update }: StepProps) {
  const { t } = useTranslation();
  return (
    <>
      <div className="mb-6 flex h-14 w-14 items-center justify-center rounded-2xl bg-saffron-100 text-saffron-700">
        <Sprout className="h-7 w-7" />
      </div>
      <h2 className="text-center font-display text-xl font-semibold text-ink-800">
        {t('onboarding.farm_title')}
      </h2>
      <p className="mt-2 text-center text-sm text-ink-600">
        {t('onboarding.farm_subtitle')}
      </p>

      <div className="mt-6 w-full space-y-4">
        <div>
          <label className="label" htmlFor="onb-farm-size">
            {t('onboarding.farm_size')}
          </label>
          <input
            id="onb-farm-size"
            type="text"
            value={form.farmSize}
            onChange={(e) => update('farmSize', e.target.value)}
            placeholder={t('onboarding.farm_size_ph')}
            className="input-lg"
            maxLength={50}
          />
        </div>

        <div>
          <label className="label" htmlFor="onb-crops">
            {t('onboarding.farm_crops')}
          </label>
          <input
            id="onb-crops"
            type="text"
            value={form.crops}
            onChange={(e) => update('crops', e.target.value)}
            placeholder={t('onboarding.farm_crops_ph')}
            className="input-lg"
            maxLength={100}
          />
          <p className="help-text">{t('onboarding.farm_crops_help')}</p>
        </div>
      </div>
    </>
  );
}

/* ============================================================
   Step 3 — Done
   ============================================================ */
function DoneStep({ form }: { form: FormState }) {
  const { t } = useTranslation();
  const hasAny =
    form.city || form.state || form.farmSize || form.crops;

  return (
    <>
      <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-leaf-100 text-leaf-700">
        <CheckCircle2 className="h-8 w-8" />
      </div>
      <h2 className="text-center font-display text-2xl font-semibold text-ink-800">
        {t('onboarding.done_title')}
      </h2>
      <p className="mt-3 text-center text-sm leading-relaxed text-ink-600">
        {t('onboarding.done_subtitle')}
      </p>

      {hasAny ? (
        <div className="mt-6 w-full">
          <p className="section-heading">{t('onboarding.done_summary')}</p>
          <div className="card space-y-2 text-sm text-ink-700">
            {form.city || form.state ? (
              <div className="flex items-center gap-2">
                <MapPin className="h-4 w-4 text-leaf-600" />
                <span>{[form.city, form.state].filter(Boolean).join(', ')}</span>
              </div>
            ) : null}
            {form.farmSize ? (
              <div className="flex items-center gap-2">
                <Sprout className="h-4 w-4 text-saffron-600" />
                <span>{form.farmSize}</span>
              </div>
            ) : null}
            {form.crops ? (
              <div className="flex items-center gap-2">
                <Leaf className="h-4 w-4 text-leaf-600" />
                <span>{form.crops}</span>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      <p className="mt-4 text-center text-xs text-ink-500">
        {t('onboarding.done_edit_hint')}
      </p>
    </>
  );
}
