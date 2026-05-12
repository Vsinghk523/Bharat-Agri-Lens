import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { api } from '@/lib/api';
import type { DiagnosticRead, FollowupRead } from '@bal/types';

export default function Result() {
  const { t } = useTranslation();
  const { diagnosticId } = useParams<{ diagnosticId: string }>();
  const [diag, setDiag] = useState<DiagnosticRead | null>(null);
  const [followups, setFollowups] = useState<FollowupRead[]>([]);
  const [showAlt, setShowAlt] = useState(false);

  useEffect(() => {
    if (!diagnosticId) return;
    api.diagnostics.get(diagnosticId).then(setDiag);
    api.diagnostics.listFollowups(diagnosticId).then(setFollowups);
  }, [diagnosticId]);

  if (!diag) return <p className="py-8 text-center text-soil-500">{t('result.loading')}</p>;

  return (
    <section className="space-y-4 py-6">
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

      {diag.secondary_predictions && (
        <button
          type="button"
          onClick={() => setShowAlt((v) => !v)}
          className="btn-secondary"
        >
          {showAlt ? t('result.hide_alt') : t('result.show_alt')}
        </button>
      )}
      {showAlt && (
        <pre className="card overflow-auto text-xs">
          {JSON.stringify(diag.secondary_predictions, null, 2)}
        </pre>
      )}
    </section>
  );
}
