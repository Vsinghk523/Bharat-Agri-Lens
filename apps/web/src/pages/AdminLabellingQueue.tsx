import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '@/lib/api';
import { useRequireAdmin } from '@/lib/auth';
import type {
  LabellingQueueItem,
  LabellingQueueSource,
  LlmFallbackSummaryResponse,
  LlmFallbackSummaryRow,
  ReviewerCorrection,
} from '@bal/types';

const PAGE_SIZE = 24;

/**
 * Admin review console.
 *
 * Two tabs control which review bucket is shown:
 *
 *   - "Flagged" (default): user-marked incorrect/partial diagnoses.
 *     Reviewing these corrects model errors and feeds the next
 *     training run with hard-negatives the model got wrong.
 *
 *   - "LLM gold": Gemini-fallback diagnoses the user marked correct.
 *     These are the highest-value rows for *expanding* PlantViT's
 *     class list — the crop wasn't in our model, the LLM nailed it,
 *     and the farmer agreed. Agronomist verification on a sample
 *     here is the cheapest path to a new trained crop.
 *
 * Above the queue, a "Coverage signals" panel summarises the
 * llm_fallback traffic over the last 7/30 days, grouped by crop.
 * The top of the table answers the operational question "what crops
 * should we add to PlantViT next?".
 */
export default function AdminLabellingQueue() {
  useRequireAdmin();
  const { t } = useTranslation();
  const [source, setSource] = useState<LabellingQueueSource>('flagged');
  const [items, setItems] = useState<LabellingQueueItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);

  const [summary, setSummary] = useState<LlmFallbackSummaryResponse | null>(null);
  const [summaryDays, setSummaryDays] = useState(7);

  const load = useCallback(
    async (off: number, src: LabellingQueueSource) => {
      setLoading(true);
      try {
        const resp = await api.admin.labellingQueue(PAGE_SIZE, off, src);
        setItems(resp.items);
        setTotal(resp.total);
        setOffset(off);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    load(0, source);
  }, [load, source]);

  const loadSummary = useCallback(async (days: number) => {
    try {
      const resp = await api.admin.llmFallbackSummary(days, 20);
      setSummary(resp);
    } catch {
      /* non-fatal — the queue still works without the panel */
    }
  }, []);

  useEffect(() => {
    loadSummary(summaryDays);
  }, [loadSummary, summaryDays]);

  async function saveCorrection(
    diagnostic_id: string,
    payload: ReviewerCorrection,
  ): Promise<void> {
    const updated = await api.admin.correctDiagnostic(diagnostic_id, payload);
    setItems((prev) =>
      prev.map((it) => (it.diagnostic_id === diagnostic_id ? updated : it)),
    );
    setEditing(null);
  }

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const pageIndex = Math.floor(offset / PAGE_SIZE);

  return (
    <section className="space-y-4 py-4">
      <header className="flex items-end justify-between">
        <div>
          <h2 className="text-2xl font-semibold text-leaf-700">
            {t('admin.title')}
          </h2>
          <p className="text-xs text-soil-500">
            {t('admin.subtitle', { total })}
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <button
            type="button"
            disabled={offset === 0 || loading}
            onClick={() => load(Math.max(0, offset - PAGE_SIZE), source)}
            className="btn-secondary disabled:opacity-50"
          >
            ‹
          </button>
          <span className="text-soil-500">
            {pageIndex + 1} / {pageCount}
          </span>
          <button
            type="button"
            disabled={offset + PAGE_SIZE >= total || loading}
            onClick={() => load(offset + PAGE_SIZE, source)}
            className="btn-secondary disabled:opacity-50"
          >
            ›
          </button>
        </div>
      </header>

      {/* Coverage signals panel: aggregate llm_fallback by crop */}
      <CoveragePanel
        summary={summary}
        days={summaryDays}
        onDaysChange={setSummaryDays}
      />

      {/* Source tabs — switch between "Flagged" and "LLM gold" buckets */}
      <div className="flex gap-1 rounded-lg bg-ink-100 p-1">
        <TabButton
          active={source === 'flagged'}
          onClick={() => setSource('flagged')}
          label={t('admin.tab_flagged')}
        />
        <TabButton
          active={source === 'llm_gold'}
          onClick={() => setSource('llm_gold')}
          label={t('admin.tab_llm_gold')}
        />
      </div>

      {loading && (
        <p className="text-sm text-soil-500">{t('admin.loading')}</p>
      )}
      {!loading && items.length === 0 && (
        <p className="text-sm text-soil-500">
          {source === 'llm_gold'
            ? t('admin.llm_gold_empty')
            : t('admin.empty')}
        </p>
      )}

      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item) => (
          <li key={item.diagnostic_id} className="card space-y-2">
            {item.image_url ? (
              // eslint-disable-next-line jsx-a11y/img-redundant-alt
              <img
                src={item.image_url}
                alt={`Diagnostic ${item.diagnostic_id}`}
                loading="lazy"
                className="aspect-square w-full rounded object-cover"
              />
            ) : (
              <div className="aspect-square w-full rounded bg-leaf-100" />
            )}
            <div className="space-y-1 text-xs">
              {/* Source badge — important visual signal that this row
                  came from Gemini, not the specialist. Hidden for
                  plantvit rows to avoid noise. */}
              {item.prediction_source === 'llm_fallback' ? (
                <p>
                  <span className="rounded bg-saffron-100 px-1 text-saffron-800">
                    ✨ {t('admin.source_llm_short')}
                  </span>
                </p>
              ) : null}
              <p>
                <span className="font-medium text-leaf-700">
                  {t('admin.predicted')}:
                </span>{' '}
                {item.predicted_plant ?? '—'} ·{' '}
                {item.predicted_disease ?? '—'} ·{' '}
                <span className="rounded bg-leaf-100 px-1">
                  {item.predicted_infection_type ?? '—'}
                </span>
              </p>
              <p>
                <span className="font-medium text-leaf-700">
                  {t('admin.feedback')}:
                </span>{' '}
                <span
                  className={
                    item.user_feedback === 'incorrect'
                      ? 'rounded bg-red-50 px-1 text-red-700'
                      : item.user_feedback === 'correct'
                        ? 'rounded bg-green-50 px-1 text-green-700'
                        : 'rounded bg-amber-50 px-1 text-amber-800'
                  }
                >
                  {item.user_feedback || '—'}
                </span>
              </p>
              {item.reviewed_by && (
                <p className="rounded bg-leaf-100 px-1 py-0.5 text-leaf-700">
                  ✓ {t('admin.reviewed_by', { id: item.reviewed_by })}
                </p>
              )}
              {(item.correct_plant ||
                item.correct_disease ||
                item.correct_infection_type) && (
                <p className="text-soil-700">
                  <span className="font-medium">{t('admin.corrected')}:</span>{' '}
                  {item.correct_plant ?? item.predicted_plant ?? '—'} ·{' '}
                  {item.correct_disease ?? item.predicted_disease ?? '—'} ·{' '}
                  <span className="rounded bg-leaf-100 px-1">
                    {item.correct_infection_type ??
                      item.predicted_infection_type ??
                      '—'}
                  </span>
                </p>
              )}
            </div>

            {editing === item.diagnostic_id ? (
              <CorrectionForm
                item={item}
                onCancel={() => setEditing(null)}
                onSave={(payload) =>
                  saveCorrection(item.diagnostic_id, payload)
                }
              />
            ) : (
              <button
                type="button"
                onClick={() => setEditing(item.diagnostic_id)}
                className="btn-secondary w-full text-xs"
              >
                {item.reviewed_by ? t('admin.edit_again') : t('admin.edit')}
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function TabButton({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        active
          ? 'flex-1 rounded-md bg-white px-3 py-1.5 text-sm font-semibold text-leaf-700 shadow-card'
          : 'flex-1 rounded-md px-3 py-1.5 text-sm font-medium text-ink-600 hover:bg-ink-200'
      }
    >
      {label}
    </button>
  );
}

/**
 * Coverage panel — the operational view for "what crops should we
 * add to PlantViT next?". Aggregates llm_fallback rows by crop with
 * a feedback breakdown. Sorted by total volume — the top entries are
 * where the LLM fallback is doing the most work, which is where the
 * specialist model is least covering us today.
 */
function CoveragePanel({
  summary,
  days,
  onDaysChange,
}: {
  summary: LlmFallbackSummaryResponse | null;
  days: number;
  onDaysChange: (d: number) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="card space-y-3">
      <div className="flex items-baseline justify-between">
        <div>
          <h3 className="text-sm font-semibold text-ink-800">
            {t('admin.coverage_heading')}
          </h3>
          <p className="text-xs text-soil-500">
            {summary
              ? t('admin.coverage_subtitle', {
                  total: summary.total_fallback_rows,
                  days,
                })
              : t('admin.loading')}
          </p>
        </div>
        <div className="flex gap-1 text-xs">
          {[7, 30, 90].map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => onDaysChange(d)}
              className={
                d === days
                  ? 'rounded-md bg-leaf-600 px-2 py-1 font-semibold text-white'
                  : 'rounded-md bg-ink-100 px-2 py-1 text-ink-700 hover:bg-ink-200'
              }
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {summary && summary.items.length === 0 ? (
        <p className="text-sm text-soil-500">
          {t('admin.coverage_empty')}
        </p>
      ) : null}

      {summary && summary.items.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-ink-100 text-left text-ink-600">
                <th className="py-1.5 pr-2">{t('admin.coverage_col_crop')}</th>
                <th className="py-1.5 pr-2 text-right">
                  {t('admin.coverage_col_total')}
                </th>
                <th className="py-1.5 pr-2 text-right">
                  {t('admin.coverage_col_correct')}
                </th>
                <th className="py-1.5 pr-2 text-right">
                  {t('admin.coverage_col_incorrect')}
                </th>
                <th className="py-1.5 pr-2 text-right">
                  {t('admin.coverage_col_partial')}
                </th>
                <th className="py-1.5 text-right">
                  {t('admin.coverage_col_none')}
                </th>
              </tr>
            </thead>
            <tbody>
              {summary.items.map((row) => (
                <CoverageRow key={row.plant_classification} row={row} />
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

function CoverageRow({ row }: { row: LlmFallbackSummaryRow }) {
  // Correct-feedback rate is the headline metric — high values mean
  // Gemini is confident AND the farmer agreed. >70% is the rough
  // threshold for "this crop is ready to migrate into PlantViT".
  const correctRate =
    row.total_count > 0
      ? Math.round((row.feedback_correct / row.total_count) * 100)
      : 0;
  const accent =
    correctRate >= 70
      ? 'text-green-700'
      : correctRate >= 40
        ? 'text-amber-700'
        : 'text-ink-700';
  return (
    <tr className="border-b border-ink-100 last:border-b-0">
      <td className="py-1.5 pr-2 font-medium text-ink-800">
        {row.plant_classification}
      </td>
      <td className="py-1.5 pr-2 text-right">{row.total_count}</td>
      <td className={`py-1.5 pr-2 text-right ${accent}`}>
        {row.feedback_correct}
        <span className="ml-0.5 text-ink-400">({correctRate}%)</span>
      </td>
      <td className="py-1.5 pr-2 text-right text-ink-600">
        {row.feedback_incorrect}
      </td>
      <td className="py-1.5 pr-2 text-right text-ink-600">
        {row.feedback_partial}
      </td>
      <td className="py-1.5 text-right text-ink-400">{row.feedback_none}</td>
    </tr>
  );
}

const INFECTION_TYPES = [
  'insect_pest',
  'fungal',
  'viral',
  'bacterial',
  'nematode',
  'nutrient_deficiency',
  'abiotic_stress',
  'weed_competition',
  'unknown',
];

interface CorrectionFormProps {
  item: LabellingQueueItem;
  onSave: (payload: ReviewerCorrection) => Promise<void>;
  onCancel: () => void;
}

function CorrectionForm({ item, onSave, onCancel }: CorrectionFormProps) {
  const { t } = useTranslation();
  const [plant, setPlant] = useState(
    item.correct_plant ?? item.predicted_plant ?? '',
  );
  const [disease, setDisease] = useState(
    item.correct_disease ?? item.predicted_disease ?? '',
  );
  const [infection, setInfection] = useState(
    item.correct_infection_type ?? item.predicted_infection_type ?? '',
  );
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      await onSave({
        correct_plant: plant || null,
        correct_disease: disease || null,
        correct_infection_type: infection || null,
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2 rounded border border-leaf-100 bg-leaf-50 p-2 text-xs">
      <label className="block">
        <span className="text-soil-700">{t('admin.plant')}</span>
        <input
          value={plant}
          onChange={(e) => setPlant(e.target.value)}
          className="mt-0.5 w-full rounded border px-2 py-1"
        />
      </label>
      <label className="block">
        <span className="text-soil-700">{t('admin.disease')}</span>
        <input
          value={disease}
          onChange={(e) => setDisease(e.target.value)}
          className="mt-0.5 w-full rounded border px-2 py-1"
        />
      </label>
      <label className="block">
        <span className="text-soil-700">{t('admin.infection_type')}</span>
        <select
          value={infection}
          onChange={(e) => setInfection(e.target.value)}
          className="mt-0.5 w-full rounded border bg-white px-2 py-1"
        >
          <option value="">—</option>
          {INFECTION_TYPES.map((k) => (
            <option key={k} value={k}>
              {t(`infection_type.${k}`, k)}
            </option>
          ))}
        </select>
      </label>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={submit}
          disabled={busy}
          className="btn-primary flex-1 text-xs disabled:opacity-50"
        >
          {busy ? '…' : t('admin.save')}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className="btn-secondary flex-1 text-xs"
        >
          {t('admin.cancel')}
        </button>
      </div>
    </div>
  );
}
