import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { api } from '@/lib/api';
import { useRequireAuth } from '@/lib/auth';
import type { DiagnosticRead, FollowupRead } from '@bal/types';

export default function Result() {
  useRequireAuth();
  const { t, i18n } = useTranslation();
  const { diagnosticId } = useParams<{ diagnosticId: string }>();
  const [diag, setDiag] = useState<DiagnosticRead | null>(null);
  const [followups, setFollowups] = useState<FollowupRead[]>([]);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [showAlt, setShowAlt] = useState(false);

  // BCP-47 tag for the API (hi-IN, ta-IN, …). Bundled languages are
  // 2-letter codes (hi, ta); the language selector emits 2-letter, so
  // append "-IN" for the diagnostic endpoint's expectations.
  const apiLang = i18n.resolvedLanguage
    ? i18n.resolvedLanguage.includes('-')
      ? i18n.resolvedLanguage
      : `${i18n.resolvedLanguage}-IN`
    : 'en-IN';

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
          // Image gone or no longer ours — fall back to no preview.
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

  if (!diag) return <p className="py-8 text-center text-soil-500">{t('result.loading')}</p>;

  return (
    <section className="space-y-4 py-6">
      {imageUrl && (
        <img
          src={imageUrl}
          alt={diag.plant_classification ?? ''}
          loading="lazy"
          className="max-h-80 w-full rounded-lg object-cover shadow-sm"
        />
      )}
      <div className="card space-y-2">
        <h2 className="text-2xl font-semibold text-leaf-700">{diag.plant_classification ?? '—'}</h2>
        {diag.scientific_name && (
          <p className="text-sm italic text-soil-500">{diag.scientific_name}</p>
        )}
        <div className="flex flex-wrap gap-2 text-xs">
          {diag.infection_type && (
            <span className="rounded bg-leaf-100 px-2 py-1 text-leaf-700">
              {t(`infection_type.${diag.infection_type}`, diag.infection_type)}
            </span>
          )}
          {diag.severity && (
            <span className="rounded bg-soil-50 px-2 py-1 text-soil-900">{diag.severity}</span>
          )}
          {diag.confidence_score != null && (
            <span className="rounded bg-leaf-100 px-2 py-1 text-leaf-700">
              {(Number(diag.confidence_score) * 100).toFixed(1)}%
            </span>
          )}
        </div>
        {diag.disease_name && <p className="text-sm">{diag.disease_name}</p>}
      </div>

      {diag.suggested_remedies && (
        <div className="card space-y-2">
          <h3 className="font-semibold text-leaf-700">{t('result.remedies')}</h3>
          <p className="whitespace-pre-line text-sm">{diag.suggested_remedies}</p>
        </div>
      )}

      {diag.preventive_measures && (
        <div className="card space-y-2">
          <h3 className="font-semibold text-leaf-700">{t('result.prevention')}</h3>
          <p className="whitespace-pre-line text-sm">{diag.preventive_measures}</p>
        </div>
      )}

      {followups.length > 0 && (
        <div className="card space-y-2">
          <h3 className="font-semibold text-leaf-700">{t('result.followups')}</h3>
          <ul className="space-y-1">
            {followups.map((f) => (
              <li key={f.addnl_question_id}>
                <button
                  type="button"
                  onClick={() => api.diagnostics.markFollowupClicked(f.addnl_question_id)}
                  className="text-left text-sm text-leaf-700 hover:underline"
                >
                  • {f.question_text}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {Array.isArray(diag.secondary_predictions) && diag.secondary_predictions.length > 0 && (
        <>
          <button
            type="button"
            onClick={() => setShowAlt((v) => !v)}
            className="btn-secondary"
          >
            {showAlt ? t('result.hide_alt') : t('result.show_alt')}
          </button>
          {showAlt && (
            <div className="card space-y-2">
              <ul className="space-y-1.5 text-sm">
                {(diag.secondary_predictions as Array<{
                  disease_name?: string | null;
                  confidence?: number | null;
                }>).map((alt, idx) => (
                  <li
                    key={`${alt.disease_name ?? 'alt'}-${idx}`}
                    className="flex items-center justify-between gap-3 border-b border-leaf-100 pb-1.5 last:border-b-0 last:pb-0"
                  >
                    <span className="text-soil-900">
                      {alt.disease_name ?? '—'}
                    </span>
                    {typeof alt.confidence === 'number' && (
                      <span className="shrink-0 rounded bg-leaf-100 px-2 py-0.5 text-xs text-leaf-700">
                        {(alt.confidence * 100).toFixed(1)}%
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  );
}
