import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { api } from '@/lib/api';
import { useRequireAuth } from '@/lib/auth';
import type { DiagnosticRead } from '@bal/types';

export default function History() {
  useRequireAuth();
  const { t } = useTranslation();
  const [items, setItems] = useState<DiagnosticRead[]>([]);

  useEffect(() => {
    api.diagnostics.list().then(setItems);
  }, []);

  return (
    <section className="space-y-3 py-6">
      <h2 className="text-2xl font-semibold text-leaf-700">{t('history.title')}</h2>
      {items.length === 0 && <p className="text-sm text-soil-500">{t('history.empty')}</p>}
      <ul className="space-y-2">
        {items.map((d) => (
          <li key={d.diagnostic_id}>
            <Link to={`/result/${d.diagnostic_id}`} className="card block hover:bg-leaf-100">
              <div className="flex items-center justify-between">
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
        ))}
      </ul>
    </section>
  );
}
