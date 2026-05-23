import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Bell,
  Camera,
  ChevronRight,
  CloudRain,
  Leaf,
  Lightbulb,
  Sparkles,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useRequireAuth, getUserId } from '@/lib/auth';
import AppBar from '@/components/ui/AppBar';
import IconButton from '@/components/ui/IconButton';
import LanguageSelector from '@/components/LanguageSelector';
import { SkeletonRow } from '@/components/ui/Skeleton';
import type { DiagnosticRead } from '@bal/types';

/**
 * Home dashboard — the landing screen for authenticated users.
 *
 * Sections (vertical, top-to-bottom):
 *
 *   1. AppBar with the brand mark, notifications bell, language picker
 *   2. Greeting block — time-of-day-aware
 *   3. Hero CTA card — single primary action ("Quick scan")
 *   4. Weekly stats — 3-tile counter row
 *   5. Recent diagnoses — list of last 3 scans
 *   6. Daily tip — small advisory card
 *
 * The recent-diagnoses + stats data are pulled from the existing
 * ``api.diagnostics.list`` endpoint; if the user has zero history we
 * skip those sections and surface a friendlier first-time-user state.
 */
export default function Home() {
  useRequireAuth();
  const { t, i18n } = useTranslation();
  const userId = getUserId();
  const [items, setItems] = useState<DiagnosticRead[] | null>(null);

  const apiLang = useMemo(() => {
    const code = i18n.resolvedLanguage;
    if (!code) return 'en-IN';
    return code.includes('-') ? code : `${code}-IN`;
  }, [i18n.resolvedLanguage]);

  useEffect(() => {
    let cancelled = false;
    api.diagnostics.list(5, 0, apiLang).then(
      (list) => {
        if (!cancelled) setItems(list);
      },
      () => {
        if (!cancelled) setItems([]);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [apiLang]);

  const greeting = useMemo(() => {
    const h = new Date().getHours();
    if (h < 12) return t('home.greeting_morning');
    if (h < 17) return t('home.greeting_afternoon');
    return t('home.greeting_evening');
  }, [t]);

  const stats = useMemo(() => {
    if (!items) return { scans: 0, healthy: 0, treated: 0 };
    return {
      scans: items.length,
      healthy: items.filter((d) => (d.infection_type ?? '').toLowerCase() === 'unknown')
        .length,
      treated: items.filter((d) => d.user_feedback === 'correct').length,
    };
  }, [items]);

  return (
    <>
      <AppBar
        title={
          <span className="flex items-center gap-1.5">
            <Leaf className="h-5 w-5 text-leaf-600" />
            BharatAgriLens
          </span>
        }
        trailing={
          <div className="flex items-center gap-1">
            <LanguageSelector />
            <Link to="/notifications" aria-label="Notifications">
              <IconButton label="Notifications" badge={0}>
                <Bell className="h-5 w-5" />
              </IconButton>
            </Link>
          </div>
        }
      />

      <div className="mx-auto max-w-2xl px-4 py-5 animate-fade-in">
        {/* 1. Greeting */}
        <div className="mb-5">
          <p className="text-xs text-ink-500">{greeting} 👋</p>
          <h2 className="font-display text-2xl font-semibold text-ink-800">
            {userId ? `Hi, ${userId.slice(0, 6)}` : t('home.welcome_back')}
          </h2>
          <p className="mt-1 text-sm text-ink-500">{t('home.ready_prompt')}</p>
        </div>

        {/* 2. Hero CTA */}
        <Link
          to="/scan"
          className="group block rounded-2xl bg-gradient-to-br from-leaf-600 to-leaf-700 p-5 text-white shadow-card transition-shadow hover:shadow-hover"
        >
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-white/15 backdrop-blur">
              <Camera className="h-6 w-6" strokeWidth={2.25} />
            </div>
            <div className="flex-1">
              <h3 className="font-display text-lg font-semibold">
                {t('home.cta_quick_scan')}
              </h3>
              <p className="text-sm text-white/85">{t('home.cta_quick_scan_hint')}</p>
            </div>
            <ChevronRight className="h-5 w-5 shrink-0 opacity-80 transition-transform group-hover:translate-x-0.5" />
          </div>
        </Link>

        {/* 3. Stats */}
        <section className="mt-6">
          <h3 className="section-heading">{t('home.stats_section')}</h3>
          <div className="grid grid-cols-3 gap-2">
            <StatTile value={stats.scans} label={t('home.stats_scans')} accent="leaf" />
            <StatTile
              value={stats.healthy}
              label={t('home.stats_healthy')}
              accent="success"
            />
            <StatTile
              value={stats.treated}
              label={t('home.stats_treated')}
              accent="saffron"
            />
          </div>
        </section>

        {/* 4. Recent diagnoses */}
        <section className="mt-6">
          <div className="mb-3 flex items-baseline justify-between">
            <h3 className="section-heading mb-0">{t('home.recent_section')}</h3>
            {items && items.length > 0 ? (
              <Link
                to="/history"
                className="text-xs font-semibold text-leaf-700 hover:text-leaf-800"
              >
                {t('home.recent_view_all')} →
              </Link>
            ) : null}
          </div>

          <div className="card divide-y divide-ink-100 p-0">
            {items === null ? (
              <>
                <SkeletonRow />
                <SkeletonRow />
              </>
            ) : items.length === 0 ? (
              <div className="px-4 py-6 text-center">
                <Sparkles className="mx-auto mb-2 h-6 w-6 text-leaf-500" />
                <p className="text-sm text-ink-600">{t('home.recent_empty')}</p>
              </div>
            ) : (
              items.slice(0, 3).map((d) => (
                <Link
                  key={d.diagnostic_id}
                  to={`/result/${d.diagnostic_id}`}
                  className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-ink-50"
                >
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-leaf-100 text-leaf-700">
                    <Leaf className="h-5 w-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-ink-800">
                      {d.plant_classification ?? t('history.unknown_plant')}
                    </p>
                    <p className="truncate text-xs text-ink-500">
                      {d.infection_type
                        ? t(`infection_type.${d.infection_type}`, d.infection_type)
                        : '—'}{' '}
                      · {formatRelative(d.add_date, t)}
                    </p>
                  </div>
                  <ChevronRight className="h-4 w-4 shrink-0 text-ink-400" />
                </Link>
              ))
            )}
          </div>
        </section>

        {/* 5. Weather / advisory card */}
        <section className="mt-6">
          <h3 className="section-heading">{t('home.weather_section')}</h3>
          <div className="card-saffron flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-saffron-200/60 text-saffron-700">
              <CloudRain className="h-4.5 w-4.5" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium text-saffron-700">
                {t('home.weather_humidity_high')}
              </p>
            </div>
          </div>
        </section>

        {/* 6. Daily tip */}
        <section className="mt-4">
          <div className="card flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-leaf-100 text-leaf-700">
              <Lightbulb className="h-4.5 w-4.5" />
            </div>
            <div className="flex-1">
              <p className="text-2xs font-semibold uppercase tracking-wider text-ink-500">
                {t('home.tips_section')}
              </p>
              <p className="mt-0.5 text-sm text-ink-800">{t('home.tip_morning_spray')}</p>
            </div>
          </div>
        </section>
      </div>
    </>
  );
}

function StatTile({
  value,
  label,
  accent,
}: {
  value: number;
  label: string;
  accent: 'leaf' | 'success' | 'saffron';
}) {
  const palette = {
    leaf: 'bg-leaf-50 text-leaf-700',
    success: 'bg-success-soft text-success',
    saffron: 'bg-saffron-50 text-saffron-700',
  }[accent];
  return (
    <div className={`${palette} rounded-xl px-3 py-3 text-center`}>
      <p className="font-display text-2xl font-semibold leading-tight">{value}</p>
      <p className="mt-0.5 text-xs">{label}</p>
    </div>
  );
}

function formatRelative(iso: string, t: ReturnType<typeof useTranslation>['t']): string {
  const date = new Date(iso);
  const now = Date.now();
  const diffSec = Math.floor((now - date.getTime()) / 1000);
  if (diffSec < 60) return t('common.now');
  if (diffSec < 3600) return t('common.minutes_ago', { count: Math.floor(diffSec / 60) });
  if (diffSec < 86400) return t('common.hours_ago', { count: Math.floor(diffSec / 3600) });
  if (diffSec < 172800) return t('common.yesterday');
  return t('common.days_ago', { count: Math.floor(diffSec / 86400) });
}
