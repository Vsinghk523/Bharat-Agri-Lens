import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { api } from '@/lib/api';
import { useRequireAuth } from '@/lib/auth';
import type { DiagnosticRead } from '@bal/types';

export default function History() {
  useRequireAuth();
  const { t, i18n } = useTranslation();
  const [items, setItems] = useState<DiagnosticRead[]>([]);
  // Map image_id -> presigned thumbnail URL (or the original URL as a
  // fallback if moderation hasn't run yet).
  const [previews, setPreviews] = useState<Record<string, string>>({});

  const apiLang = i18n.resolvedLanguage
    ? i18n.resolvedLanguage.includes('-')
      ? i18n.resolvedLanguage
      : `${i18n.resolvedLanguage}-IN`
    : 'en-IN';

  useEffect(() => {
    let cancelled = false;
    api.diagnostics.list(50, 0, apiLang).then(async (diagnostics) => {
      if (cancelled) return;
      setItems(diagnostics);

      // Fetch preview URLs in parallel; ignore failures (a missing /
      // soft-deleted upload just means no preview, not an error to
      // surface to the user here).
      const targets = diagnostics
        .map((d) => d.image_id)
        .filter((id): id is string => Boolean(id));
      const entries = await Promise.all(
        targets.map(async (id) => {
          try {
            const dl = await api.uploads.getDownloadUrl(id);
            return [id, dl.thumbnail_url ?? dl.url] as const;
          } catch {
            return null;
          }
        }),
      );
      if (cancelled) return;
      const map: Record<string, string> = {};
      for (const e of entries) if (e) map[e[0]] = e[1];
      setPreviews(map);
    });
    return () => {
      cancelled = true;
    };
  }, [apiLang]);

  return (
    <section className="space-y-3 py-6">
      <h2 className="text-2xl font-semibold text-leaf-700">{t('history.title')}</h2>
      {items.length === 0 && <p className="text-sm text-soil-500">{t('history.empty')}</p>}
      <ul className="space-y-2">
        {items.map((d) => {
          const previewUrl = d.image_id ? previews[d.image_id] : undefined;
          return (
            <li key={d.diagnostic_id}>
              <Link
                to={`/result/${d.diagnostic_id}`}
                className="card flex items-center gap-3 hover:bg-leaf-100"
              >
                {previewUrl ? (
                  <img
                    src={previewUrl}
                    alt=""
                    loading="lazy"
                    className="h-14 w-14 flex-shrink-0 rounded object-cover"
                  />
                ) : (
                  <div
                    className="h-14 w-14 flex-shrink-0 rounded bg-leaf-100"
                    aria-hidden="true"
                  />
                )}
                <div className="flex flex-1 items-center justify-between">
                  <div>
                    <p className="font-medium text-leaf-700">
                      {d.plant_classification ?? t('history.unknown_plant')}
                    </p>
                    <p className="text-xs text-soil-500">{d.disease_name ?? '—'}</p>
                  </div>
                  <span className="text-xs text-soil-500">
                    {new Date(d.add_date).toLocaleDateString()}
                  </span>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
