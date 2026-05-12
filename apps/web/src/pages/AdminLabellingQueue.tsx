import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '@/lib/api';
import { useRequireAdmin } from '@/lib/auth';
import type { LabellingQueueItem, ReviewerCorrection } from '@bal/types';

const PAGE_SIZE = 24;

export default function AdminLabellingQueue() {
  useRequireAdmin();
  const { t } = useTranslation();
  const [items, setItems] = useState<LabellingQueueItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);

  const load = useCallback(async (off: number) => {
    setLoading(true);
    try {
      const resp = await api.admin.labellingQueue(PAGE_SIZE, off);
      setItems(resp.items);
      setTotal(resp.total);
      setOffset(off);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(0);
  }, [load]);

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
            onClick={() => load(Math.max(0, offset - PAGE_SIZE))}
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
            onClick={() => load(offset + PAGE_SIZE)}
            className="btn-secondary disabled:opacity-50"
          >
            ›
          </button>
        </div>
      </header>

      {loading && (
        <p className="text-sm text-soil-500">{t('admin.loading')}</p>
      )}
      {!loading && items.length === 0 && (
        <p className="text-sm text-soil-500">{t('admin.empty')}</p>
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
                      : 'rounded bg-amber-50 px-1 text-amber-800'
                  }
                >
                  {item.user_feedback}
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
