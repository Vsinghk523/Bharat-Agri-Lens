import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  HelpCircle,
  Leaf,
  MessageCircle,
  Share2,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useRequireAuth } from '@/lib/auth';
import AppBar from '@/components/ui/AppBar';
import IconButton from '@/components/ui/IconButton';
import { Skeleton } from '@/components/ui/Skeleton';
import type { DiagnosticRead, FollowupRead } from '@bal/types';

/**
 * Result screen — the after-Analyze experience.
 *
 * Layout (top to bottom):
 *
 *   1. AppBar (back + Share action)
 *   2. Hero image of the uploaded plant
 *   3. Headline block: plant + scientific name + severity / confidence
 *   4. Treatment plan (suggested_remedies, formatted as numbered steps)
 *   5. Prevention card
 *   6. Followup questions list (taps to chat)
 *   7. Feedback row (thumbs up / down / unsure)
 *   8. Collapsible alternative diagnoses
 */
export default function Result() {
  useRequireAuth();
  const { t, i18n } = useTranslation();
  const { diagnosticId } = useParams<{ diagnosticId: string }>();
  const [diag, setDiag] = useState<DiagnosticRead | null>(null);
  const [followups, setFollowups] = useState<FollowupRead[]>([]);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [showAlt, setShowAlt] = useState(false);
  // The UI exposes Yes / No / Not sure as the prompt; the server-side
  // verdict enum is the more clinical correct / incorrect / partial.
  // We translate one to the other inside ``sendFeedback`` so the user
  // never sees the technical term.
  type UiVerdict = 'yes' | 'no' | 'unsure';
  const [feedbackSent, setFeedbackSent] = useState<UiVerdict | null>(null);

  const apiLang = useMemo(() => {
    const code = i18n.resolvedLanguage;
    if (!code) return 'en-IN';
    return code.includes('-') ? code : `${code}-IN`;
  }, [i18n.resolvedLanguage]);

  useEffect(() => {
    if (!diagnosticId) return;
    let cancelled = false;
    api.diagnostics.get(diagnosticId, apiLang).then(async (d) => {
      if (cancelled) return;
      setDiag(d);
      if (d.image_id) {
        try {
          const dl = await api.uploads.getDownloadUrl(d.image_id);
          if (!cancelled) setImageUrl(dl.url);
        } catch {
          /* preview optional */
        }
      }
    });
    api.diagnostics.listFollowups(diagnosticId, apiLang).then((f) => {
      if (!cancelled) setFollowups(f);
    });
    return () => {
      cancelled = true;
    };
  }, [diagnosticId, apiLang]);

  async function sendFeedback(ui: UiVerdict) {
    if (!diagnosticId || feedbackSent) return;
    setFeedbackSent(ui);
    const verdict =
      ui === 'yes' ? 'correct' : ui === 'no' ? 'incorrect' : 'partial';
    try {
      await api.diagnostics.submitFeedback(diagnosticId, { verdict });
    } catch {
      /* user feedback is fire-and-forget — don't block UI */
    }
  }

  if (!diag) {
    return (
      <>
        <AppBar showBack />
        <div className="mx-auto max-w-2xl px-4 py-6">
          <Skeleton width="w-full" height="h-64" className="mb-4 rounded-2xl" />
          <Skeleton width="w-40" height="h-6" className="mb-2" />
          <Skeleton width="w-24" height="h-4" className="mb-6" />
          <Skeleton width="w-full" height="h-24" className="mb-4 rounded-xl" />
          <Skeleton width="w-full" height="h-32" className="rounded-xl" />
        </div>
      </>
    );
  }

  // Early-return for OOD rejections: the inference layer refused to
  // diagnose this image, so all the prediction fields are null. Show a
  // friendly explanatory card instead of an empty/broken result page.
  if (diag.rejection_reason) {
    return <RejectionView diag={diag} imageUrl={imageUrl} />;
  }

  const severityKey = diag.severity ?? 'unknown';
  const severityClass =
    {
      low: 'chip-severity-low',
      medium: 'chip-severity-medium',
      high: 'chip-severity-high',
      critical: 'chip-severity-critical',
    }[severityKey] ?? 'chip-ink';

  const remedies = parseRemedies(diag.suggested_remedies);

  return (
    <>
      <AppBar
        showBack
        title={diag.plant_classification ?? '—'}
        subtitle={diag.scientific_name ?? undefined}
        trailing={
          <IconButton label="Share" onClick={() => navigator.share?.({ title: 'My BharatAgriLens diagnosis', url: window.location.href }).catch(() => {})}>
            <Share2 className="h-5 w-5" />
          </IconButton>
        }
      />

      <div className="mx-auto max-w-2xl px-4 pb-6 pt-4 animate-fade-in">
        {/* Beta-reliability banner.
            v0 of the disease classifier is trained on a narrow set of
            crops and lacks proper out-of-distribution rejection. Until
            the CLIP gate + calibration work lands (next deploy),
            farmers MUST see this warning on every result so a
            confidently-wrong prediction doesn't get acted on as
            authoritative advice. Remove this block once the OOD
            defense is in production. */}
        <div className="mb-4 flex items-start gap-3 rounded-xl border border-saffron-300 bg-saffron-50 px-4 py-3">
          <AlertTriangle className="h-5 w-5 shrink-0 text-saffron-700" />
          <div className="flex-1 text-sm">
            <p className="font-semibold text-saffron-800">
              {t('result.beta_warning_title')}
            </p>
            <p className="mt-0.5 text-saffron-700">
              {t('result.beta_warning_body')}
            </p>
          </div>
        </div>

        {/* Hero image */}
        {imageUrl ? (
          <div className="overflow-hidden rounded-2xl border border-ink-100 bg-ink-100 shadow-card">
            <img
              src={imageUrl}
              alt={diag.plant_classification ?? ''}
              loading="lazy"
              className="block aspect-[16/10] w-full object-cover"
            />
          </div>
        ) : null}

        {/* Headline + chips */}
        <section className="mt-4">
          <h2 className="font-display text-2xl font-semibold text-ink-800">
            {diag.plant_classification ?? '—'}
          </h2>
          {diag.scientific_name ? (
            <p className="text-sm italic text-ink-500">{diag.scientific_name}</p>
          ) : null}

          <div className="mt-3 flex flex-wrap items-center gap-2">
            {diag.infection_type ? (
              <span className="chip-leaf">
                <Leaf className="h-3 w-3" />
                {t(`infection_type.${diag.infection_type}`, diag.infection_type)}
              </span>
            ) : null}
            {diag.severity ? (
              <span className={severityClass}>
                <AlertTriangle className="h-3 w-3" />
                {t(`result.severity_${diag.severity}`, diag.severity)}
              </span>
            ) : null}
            {diag.confidence_score != null ? (
              <span className="chip-ink">
                {(Number(diag.confidence_score) * 100).toFixed(1)}%
              </span>
            ) : null}
            {/* LLM-fallback provenance badge. When the specialist
                model couldn't diagnose this image but Gemini was able
                to, we surface that so the farmer knows the diagnosis
                comes from a more general source — and so they
                calibrate their confidence accordingly. */}
            {diag.prediction_source === 'llm_fallback' ? (
              <span className="chip-saffron" title={t('result.source_llm_tooltip')}>
                <Sparkles className="h-3 w-3" />
                {t('result.source_llm_badge')}
              </span>
            ) : null}
          </div>

          {diag.disease_name ? (
            <p className="mt-3 text-base text-ink-700">{diag.disease_name}</p>
          ) : null}
        </section>

        {/* Treatment plan */}
        {remedies.length > 0 ? (
          <section className="mt-6">
            <div className="card">
              <div className="mb-3 flex items-center gap-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-leaf-100 text-leaf-700">
                  <Stethoscope className="h-4 w-4" />
                </span>
                <h3 className="font-display text-base font-semibold text-ink-800">
                  {t('result.treatment_section')}
                </h3>
              </div>
              <ol className="space-y-3">
                {remedies.map((step, idx) => (
                  <li key={idx} className="flex gap-3">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-leaf-600 text-xs font-semibold text-white">
                      {idx + 1}
                    </span>
                    <p className="text-sm leading-relaxed text-ink-700">{step}</p>
                  </li>
                ))}
              </ol>
            </div>
          </section>
        ) : null}

        {/* Prevention */}
        {diag.preventive_measures ? (
          <section className="mt-4">
            <div className="card-leaf">
              <div className="mb-2 flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-leaf-700" />
                <h3 className="font-display text-sm font-semibold text-leaf-800">
                  {t('result.prevention')}
                </h3>
              </div>
              <p className="text-sm leading-relaxed text-ink-700">
                {diag.preventive_measures}
              </p>
            </div>
          </section>
        ) : null}

        {/* Followups */}
        {followups.length > 0 ? (
          <section className="mt-6">
            <div className="card">
              <div className="mb-3 flex items-center gap-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-saffron-100 text-saffron-700">
                  <MessageCircle className="h-4 w-4" />
                </span>
                <div>
                  <h3 className="font-display text-base font-semibold text-ink-800">
                    {t('result.followups')}
                  </h3>
                  <p className="text-2xs text-ink-500">{t('result.followups_subtitle')}</p>
                </div>
              </div>
              <ul className="-mx-2 divide-y divide-ink-100">
                {followups.map((f) => (
                  <li key={f.addnl_question_id}>
                    <FollowupRow
                      text={f.question_text}
                      onClick={() => api.diagnostics.markFollowupClicked(f.addnl_question_id)}
                    />
                  </li>
                ))}
              </ul>
            </div>
          </section>
        ) : null}

        {/* Feedback */}
        <section className="mt-6">
          <div className="card">
            <h3 className="mb-3 text-center font-display text-sm font-semibold text-ink-800">
              {feedbackSent ? t('result.feedback_thanks') : t('result.feedback_prompt')}
            </h3>
            {!feedbackSent ? (
              <div className="grid grid-cols-3 gap-2">
                <FeedbackButton
                  label={t('result.feedback_yes')}
                  icon={<ThumbsUp className="h-4 w-4" />}
                  onClick={() => sendFeedback('yes')}
                  accent="success"
                />
                <FeedbackButton
                  label={t('result.feedback_no')}
                  icon={<ThumbsDown className="h-4 w-4" />}
                  onClick={() => sendFeedback('no')}
                  accent="danger"
                />
                <FeedbackButton
                  label={t('result.feedback_unsure')}
                  icon={<CheckCircle2 className="h-4 w-4" />}
                  onClick={() => sendFeedback('unsure')}
                  accent="ink"
                />
              </div>
            ) : null}
          </div>
        </section>

        {/* Alternative diagnoses */}
        {Array.isArray(diag.secondary_predictions) &&
        diag.secondary_predictions.length > 0 ? (
          <section className="mt-4">
            <button
              type="button"
              onClick={() => setShowAlt((v) => !v)}
              className="flex w-full items-center justify-between rounded-xl border border-ink-100 bg-white px-4 py-3 text-sm font-medium text-ink-700 transition-colors hover:border-leaf-300 hover:bg-leaf-50"
            >
              <span>
                {showAlt ? t('result.hide_alt') : t('result.show_alt')}
              </span>
              <ChevronDown
                className={`h-4 w-4 transition-transform ${showAlt ? 'rotate-180' : ''}`}
              />
            </button>

            {showAlt ? (
              <ul className="mt-2 space-y-1.5 rounded-xl border border-ink-100 bg-white p-2">
                {(
                  diag.secondary_predictions as Array<{
                    disease_name?: string | null;
                    infection_type?: string | null;
                    confidence?: number | null;
                  }>
                ).map((alt, idx) => {
                  const label =
                    alt.disease_name ??
                    (alt.infection_type
                      ? t(`infection_type.${alt.infection_type}`, alt.infection_type)
                      : '—');
                  return (
                    <li
                      key={`${label}-${idx}`}
                      className="flex items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm"
                    >
                      <span className="text-ink-700">{label}</span>
                      {typeof alt.confidence === 'number' ? (
                        <span className="chip-ink">
                          {(alt.confidence * 100).toFixed(1)}%
                        </span>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            ) : null}
          </section>
        ) : null}
      </div>
    </>
  );
}

function FollowupRow({ text, onClick }: { text: string; onClick: () => void }) {
  const nav = useNavigate();
  return (
    <button
      type="button"
      onClick={() => {
        onClick();
        nav('/chat');
      }}
      className="flex w-full items-center justify-between gap-2 rounded-lg px-2 py-2.5 text-left text-sm text-ink-700 transition-colors hover:bg-leaf-50"
    >
      <span>{text}</span>
      <ChevronRight className="h-4 w-4 shrink-0 text-ink-400" />
    </button>
  );
}

function FeedbackButton({
  label,
  icon,
  onClick,
  accent,
}: {
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
  accent: 'success' | 'danger' | 'ink';
}) {
  const palette = {
    success: 'bg-success-soft text-success hover:bg-success hover:text-white',
    danger: 'bg-danger-soft text-danger hover:bg-danger hover:text-white',
    ink: 'bg-ink-100 text-ink-700 hover:bg-ink-700 hover:text-white',
  }[accent];
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex flex-col items-center gap-1 rounded-lg px-2 py-3 text-xs font-medium transition-colors ${palette}`}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

/** Parse the predictor's numbered-list string ("1. ...\n2. ...\n3. ...")
 *  into discrete steps so we can render them as a true ordered list. */
function parseRemedies(raw: string | null | undefined): string[] {
  if (!raw) return [];
  const lines = raw.split(/\n+/).map((s) => s.trim()).filter(Boolean);
  return lines.map((l) => l.replace(/^\d+[.)]\s*/, ''));
}

/**
 * RejectionView — rendered when the inference layer's OOD defense
 * decided the image couldn't be diagnosed. Replaces the entire result
 * layout (hero image stays, but no chips/treatment/feedback rows since
 * none of those fields exist on a rejected diagnostic).
 *
 * Each rejection_reason maps to an icon, a title, and an action-
 * oriented body. The "Scan again" button routes back to /scan so the
 * farmer has a one-tap retry path.
 */
function RejectionView({
  diag,
  imageUrl,
}: {
  diag: DiagnosticRead;
  imageUrl: string | null;
}) {
  const { t } = useTranslation();
  const nav = useNavigate();
  const reason = diag.rejection_reason ?? 'low_confidence';

  // Reason → icon + accent palette. Quality issues use the soil/saffron
  // family (corrective), category issues use leaf-ink (informative),
  // confidence issues use a muted neutral (uncertain).
  const accent =
    reason === 'too_blurry' || reason === 'too_dark' || reason === 'too_small'
      ? 'saffron'
      : reason === 'not_a_plant' || reason === 'non_target_plant'
        ? 'leaf'
        : 'ink';

  const iconPalette = {
    saffron: 'bg-saffron-100 text-saffron-700',
    leaf: 'bg-leaf-100 text-leaf-700',
    ink: 'bg-ink-100 text-ink-700',
  }[accent];

  const Icon =
    reason === 'too_blurry' || reason === 'too_dark' || reason === 'too_small'
      ? Camera
      : reason === 'not_a_plant' || reason === 'non_target_plant'
        ? Leaf
        : HelpCircle;

  return (
    <>
      <AppBar showBack title={t('rejection.app_bar_title')} />
      <div className="mx-auto max-w-2xl px-4 pb-6 pt-4 animate-fade-in">
        {imageUrl ? (
          <div className="mb-4 overflow-hidden rounded-2xl border border-ink-100 bg-ink-100 shadow-card">
            <img
              src={imageUrl}
              alt=""
              loading="lazy"
              className="block aspect-[16/10] w-full object-cover"
            />
          </div>
        ) : null}

        <div className="card flex flex-col items-center text-center">
          <div
            className={`flex h-14 w-14 items-center justify-center rounded-2xl ${iconPalette}`}
          >
            <Icon className="h-7 w-7" />
          </div>
          <h2 className="mt-4 font-display text-xl font-semibold text-ink-800">
            {t(`rejection.${reason}.title`)}
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-ink-600">
            {/* If CLIP gave us a guess at what it saw (e.g. "Rose" or
                "Cat"), thread that into the body so the farmer
                understands the model's reasoning. */}
            {diag.rejection_hint
              ? t(`rejection.${reason}.body_with_hint`, { hint: diag.rejection_hint })
              : t(`rejection.${reason}.body`)}
          </p>

          <button
            type="button"
            onClick={() => nav('/scan')}
            className="btn-primary btn-lg mt-6 w-full"
          >
            <Camera className="h-4 w-4" />
            {t('rejection.scan_again')}
          </button>
        </div>

        {/* Educational tips block — generic guidance for "next time".
            Keeps the page useful even after the rejection: farmer learns
            what a good photo looks like. */}
        <div className="mt-4 card">
          <h3 className="section-heading mb-2">{t('rejection.tips_heading')}</h3>
          <ul className="space-y-1.5 text-sm text-ink-700">
            <li>• {t('rejection.tip_lighting')}</li>
            <li>• {t('rejection.tip_close')}</li>
            <li>• {t('rejection.tip_focus')}</li>
            <li>• {t('rejection.tip_single_plant')}</li>
          </ul>
        </div>
      </div>
    </>
  );
}
