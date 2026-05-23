import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Camera, ChevronRight, Leaf } from 'lucide-react';
import { api } from '@/lib/api';
import { useRequireAuth } from '@/lib/auth';
import AppBar from '@/components/ui/AppBar';
import EmptyState from '@/components/ui/EmptyState';
import { SkeletonRow } from '@/components/ui/Skeleton';
import type { DiagnosticRead } from '@bal/types';

export default function History() {
  useRequireAuth();
  const { t, i18n } = useTranslation();
  const [items, setItems] = useState<DiagnosticRead[] | null>(null);
  const [previews, setPreviews] = useState<Record<string, string>>({});

  const apiLang = useMemo(() => {
    const code = i18n.resolvedLanguage;
    if (!code) return 'en-IN';
    return code.includes('-') ? code : `${code}-IN`;
  }, [i18n.resolvedLanguage]);

  useEffect(() => {
    let cancelled = false;
    api.diagnostics.list(50, 0, apiLang).then(async (diagnostics) => {
      if (cancelled) return;
      setItems(diagnostics);

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
    <>
      <AppBar title={t('history.title')} subtitle={t('history.subtitle')} />

      <div className="mx-auto max-w-2xl px-4 py-4 animate-fade-in">
        {items === null ? (
          <div className="card divide-y divide-ink-100 p-0">
            <SkeletonRow />
            <SkeletonRow />
            <SkeletonRow />
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            icon={<Leaf className="h-6 w-6" />}
            title={t('history.empty_title')}
            description={t('history.empty_subtitle')}
            action={
              <Link to="/scan" className="btn-primary">
                <Camera className="h-4 w-4" />
                {t('history.empty_cta')}
              </Link>
            }
          />
        ) : (
          <ul className="space-y-2">
            {items.map((d) => {
              const previewUrl = d.image_id ? previews[d.image_id] : undefined;
              return (
                <li key={d.diagnostic_id}>
                  <Link
                    to={`/result/${d.diagnostic_id}`}
                    className="card-tap flex items-center gap-3 p-3"
                  >
                    {previewUrl ? (
                      <img
                        src={previewUrl}
                        alt=""
                        loading="lazy"
                        className="h-14 w-14 shrink-0 rounded-lg object-cover"
                      />
                    ) : (
                      <div
                        className="flex h-14 w-14 shrink-0 items-center justify-center rounded-lg bg-leaf-100 text-leaf-700"
                        aria-hidden="true"
                      >
                        <Leaf className="h-5 w-5" />
                      </div>
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium text-ink-800">
                        {d.plant_classification ?? t('history.unknown_plant')}
                      </p>
                      <p className="truncate text-xs text-ink-500">
                        {d.disease_name ?? '—'}
                      </p>
                      <p className="mt-0.5 text-2xs text-ink-400">
                        {new Date(d.add_date).toLocaleDateString(undefined, {
                          day: 'numeric',
                          month: 'short',
                          year: 'numeric',
                        })}
                      </p>
                    </div>
                    <ChevronRight className="h-4 w-4 shrink-0 text-ink-400" />
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </>
  );
}
