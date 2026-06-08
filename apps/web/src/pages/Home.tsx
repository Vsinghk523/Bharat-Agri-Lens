import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  Bell,
  Camera,
  ChevronRight,
  CloudRain,
  Leaf,
  Lightbulb,
  Plus,
  Sparkles,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useRequireAuth, getUserId, getUserName } from '@/lib/auth';
import AppBar from '@/components/ui/AppBar';
import IconButton from '@/components/ui/IconButton';
import LanguageSelector from '@/components/LanguageSelector';
import type {
  DiagnosticRead,
  TreatmentProgressRead,
  UserRead,
} from '@bal/types';

interface OutbreakItem {
  pincode: string;
  infection_type: string;
  report_count: number;
  notified_at: string;
}

/**
 * Home dashboard — landing screen for authenticated users.
 *
 * Hybrid layout: Direction A's crop-focused hero + Direction B's
 * "In your area" outbreak panel. The hero is the centrepiece — it
 * answers "what's happening with my crops right now?" in one glance.
 * Everything else orbits it: crop chips for quick filter, a recent-
 * scans strip with photo thumbnails, the area panel for hyperlocal
 * pest pressure, and a compact weather + tip pair at the bottom.
 *
 * Hero state machine
 * ------------------
 * The hero card renders in one of three modes depending on what we
 * know about the user:
 *
 *   - ``active``  : at least one recent (last 30 days) diagnosis
 *                   with a real infection (not 'unknown', not
 *                   'low' severity, not OOD-rejected). Most recent
 *                   such row becomes the focus.
 *   - ``healthy`` : the user has scans but none currently need
 *                   treatment. Celebrate; show "all clear".
 *   - ``empty``   : no scans yet. Show "first scan" prompt.
 *
 * The "In your area" panel is hidden until Trigger #3 ships an
 * endpoint that returns nearby outbreak data; for now the
 * conditional render falls through silently.
 */

const ACTIVE_WINDOW_DAYS = 30;

/** Emoji map for common Indian crops. Falls back to Leaf icon for
 *  anything not recognised. Kept small and conservative — better an
 *  abstract leaf than a confusing emoji for the wrong crop. */
const CROP_EMOJI: Record<string, string> = {
  tomato: '🍅',
  potato: '🥔',
  brinjal: '🍆',
  eggplant: '🍆',
  chilli: '🌶️',
  pepper: '🌶️',
  mango: '🥭',
  apple: '🍎',
  orange: '🍊',
  grape: '🍇',
  strawberry: '🍓',
  wheat: '🌾',
  rice: '🌾',
  paddy: '🌾',
  corn: '🌽',
  maize: '🌽',
  cotton: '☁️',
  sugarcane: '🎋',
  onion: '🧅',
  garlic: '🧄',
  soybean: '🫘',
  peanut: '🥜',
  groundnut: '🥜',
};

function cropEmoji(name: string | null | undefined): string | null {
  if (!name) return null;
  const key = name.toLowerCase().trim();
  return CROP_EMOJI[key] ?? null;
}

/** Parse the comma-separated crops the farmer entered during onboarding. */
function parseCropList(raw: string | null | undefined): string[] {
  if (!raw) return [];
  return raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 8); // bound the chip row at 8 — anything beyond drifts off-screen
}

export default function Home() {
  useRequireAuth();
  const { t, i18n } = useTranslation();
  const userId = getUserId();
  const userName = getUserName();

  const [items, setItems] = useState<DiagnosticRead[] | null>(null);
  const [me, setMe] = useState<UserRead | null>(null);
  const [outbreak, setOutbreak] = useState<OutbreakItem | null>(null);
  const [progress, setProgress] = useState<TreatmentProgressRead | null>(null);

  // Greeting name: prefer user_name (first token only — "Vivek Singh" → "Vivek").
  const greetingName =
    userName?.trim()?.split(/\s+/)?.[0] ||
    (userId ? userId.slice(0, 6) : null);

  const apiLang = useMemo(() => {
    const code = i18n.resolvedLanguage;
    if (!code) return 'en-IN';
    return code.includes('-') ? code : `${code}-IN`;
  }, [i18n.resolvedLanguage]);

  const loadDiagnostics = useCallback(async () => {
    try {
      const list = await api.diagnostics.list(8, 0, apiLang);
      setItems(list);
    } catch {
      setItems([]);
    }
  }, [apiLang]);

  useEffect(() => {
    loadDiagnostics();
  }, [loadDiagnostics]);

  useEffect(() => {
    let cancelled = false;
    api.users.me().then(
      (u) => {
        if (!cancelled) setMe(u);
      },
      () => {
        /* non-fatal */
      },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  // Hyperlocal outbreak alerts. Empty list (or fetch failure) leaves
  // ``outbreak`` null, which makes the panel disappear silently.
  useEffect(() => {
    let cancelled = false;
    api.users.myOutbreakAlerts().then(
      (resp) => {
        if (cancelled) return;
        const head = resp.items[0] ?? null;
        if (head) setOutbreak(head);
      },
      () => {
        /* non-fatal — pre-Trigger#3 deploys 404 here; we just hide. */
      },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  const greeting = useMemo(() => {
    const h = new Date().getHours();
    if (h < 12) return t('home.greeting_morning');
    if (h < 17) return t('home.greeting_afternoon');
    return t('home.greeting_evening');
  }, [t]);

  // Hero state: pick the most recent meaningful diagnosis.
  const activeDiagnosis = useMemo(() => {
    if (!items || items.length === 0) return null;
    const now = Date.now();
    const cutoff = now - ACTIVE_WINDOW_DAYS * 24 * 60 * 60 * 1000;
    // Most recent diagnosis that:
    //  - happened within ACTIVE_WINDOW_DAYS
    //  - wasn't OOD-rejected
    //  - has a known infection_type (not 'unknown')
    //  - has severity above 'low' (low = optional treatment)
    return (
      items.find((d) => {
        if (d.rejection_reason) return false;
        const dt = new Date(d.add_date).getTime();
        if (Number.isNaN(dt) || dt < cutoff) return false;
        const it = (d.infection_type ?? '').toLowerCase();
        if (!it || it === 'unknown') return false;
        const sev = (d.severity ?? '').toLowerCase();
        return sev === 'medium' || sev === 'high' || sev === 'critical';
      }) ?? null
    );
  }, [items]);

  const heroMode: 'active' | 'healthy' | 'empty' = items === null
    ? 'empty' // still loading — treat like empty; skeleton handles visuals
    : items.length === 0
      ? 'empty'
      : activeDiagnosis
        ? 'active'
        : 'healthy';

  // Treatment-cycle progress for the active diagnosis. Only fetched
  // when there's an active issue worth treating — the endpoint
  // tolerates being asked about diagnoses with no reminders
  // (returns total_steps=0), but skipping the round-trip in the
  // healthy/empty cases keeps Home snappy. Re-runs whenever the
  // active diagnosis itself changes (e.g. user scans a new plant).
  useEffect(() => {
    if (!activeDiagnosis) {
      setProgress(null);
      return;
    }
    let cancelled = false;
    api.diagnostics
      .treatmentProgress(activeDiagnosis.diagnostic_id)
      .then(
        (p) => {
          if (!cancelled) setProgress(p);
        },
        () => {
          // Pre-deploy clients hit a 404; pre-data hit a row count
          // that's still being committed. Either way, hide the
          // indicator silently — the rest of the hero still renders.
          if (!cancelled) setProgress(null);
        },
      );
    return () => {
      cancelled = true;
    };
  }, [activeDiagnosis]);

  const cropChips = useMemo(() => parseCropList(me?.default_crop_interest), [me]);

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

      <div className="mx-auto max-w-2xl px-4 py-4 animate-fade-in">
        {/* Greeting */}
        <div className="mb-4">
          <p className="text-xs text-ink-500">{greeting} 👋</p>
          <h2 className="font-display text-2xl font-semibold text-ink-800">
            {greetingName ? t('home.hi_name', { name: greetingName }) : t('home.welcome_back')}
          </h2>
        </div>

        {/* HERO — the centrepiece */}
        {heroMode === 'active' && activeDiagnosis ? (
          <ActiveHero
            diag={activeDiagnosis}
            loading={items === null}
            progress={progress}
          />
        ) : heroMode === 'healthy' ? (
          <HealthyHero latest={items?.[0] ?? null} />
        ) : (
          <EmptyHero loading={items === null} />
        )}

        {/* My crops chips */}
        {cropChips.length > 0 || me ? (
          <section className="mt-5">
            <div className="mb-2 flex items-baseline justify-between">
              <h3 className="section-heading mb-0">{t('home.crops_section')}</h3>
              <Link
                to="/profile"
                className="text-xs font-semibold text-leaf-700 hover:text-leaf-800"
              >
                {t('home.crops_manage')} →
              </Link>
            </div>
            <div className="-mx-4 px-4 flex gap-2 overflow-x-auto no-scrollbar">
              {cropChips.map((name) => (
                <CropChip key={name} name={name} />
              ))}
              <Link
                to="/profile"
                className="flex shrink-0 items-center gap-1 rounded-full border border-dashed border-leaf-200 bg-leaf-50 px-3.5 py-1.5 text-xs font-medium text-leaf-700 hover:bg-leaf-100"
              >
                <Plus className="h-3 w-3" />
                {t('home.crops_add')}
              </Link>
            </div>
          </section>
        ) : null}

        {/* In your area — Trigger #3 hyperlocal outbreak alerts.
            Renders only when the user has both:
            (a) a pincode set, and
            (b) a recent outbreak alert recorded for their pincode in
                the outbreak_alerts table (populated by the daily
                detection cron).
            When either is missing the panel disappears silently. */}
        {outbreak && me?.pincode ? (
          <InYourAreaPanel outbreak={outbreak} pincode={me.pincode} />
        ) : null}

        {/* Recent scans — horizontal scroll thumbnails */}
        <section className="mt-5">
          <div className="mb-2 flex items-baseline justify-between">
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

          {items === null ? (
            <RecentSkeleton />
          ) : items.length === 0 ? (
            <div className="card flex items-center gap-3 py-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-leaf-100 text-leaf-700">
                <Sparkles className="h-4 w-4" />
              </div>
              <p className="text-sm text-ink-600">{t('home.recent_empty')}</p>
            </div>
          ) : (
            <div className="-mx-4 px-4 flex gap-3 overflow-x-auto no-scrollbar pb-1">
              {items.slice(0, 6).map((d) => (
                <ScanCard key={d.diagnostic_id} diag={d} />
              ))}
            </div>
          )}
        </section>

        {/* Today: compact weather + tip duo */}
        <section className="mt-5 grid grid-cols-2 gap-2.5">
          <div className="rounded-xl border-l-4 border-saffron-400 bg-gradient-to-br from-saffron-50 to-white p-3 shadow-card">
            <div className="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wider text-saffron-700">
              <CloudRain className="h-3.5 w-3.5" />
              {t('home.weather_section')}
            </div>
            <p className="mt-1 text-xs leading-snug text-ink-700">
              {t('home.weather_humidity_high')}
            </p>
          </div>
          <div className="rounded-xl border-l-4 border-leaf-500 bg-gradient-to-br from-leaf-50 to-white p-3 shadow-card">
            <div className="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wider text-leaf-700">
              <Lightbulb className="h-3.5 w-3.5" />
              {t('home.tips_section')}
            </div>
            <p className="mt-1 text-xs leading-snug text-ink-700">
              {t('home.tip_morning_spray')}
            </p>
          </div>
        </section>
      </div>
    </>
  );
}

/* ============================================================
   Hero variants
   ============================================================ */

interface ActiveHeroProps {
  diag: DiagnosticRead;
  loading: boolean;
  /** Current step of the 3-step treatment cycle. Null until the
   *  fetch resolves; ``total_steps === 0`` means no reminders
   *  scheduled (UI hides the progress block). */
  progress: TreatmentProgressRead | null;
}

function ActiveHero({ diag, progress }: ActiveHeroProps) {
  const { t } = useTranslation();
  const emoji = cropEmoji(diag.plant_classification) ?? '🌿';
  const severityKey = (diag.severity ?? 'medium').toLowerCase();

  // Decide whether to show the "Step N of 3" block. Hidden when:
  //   - the fetch hasn't resolved yet (progress === null)
  //   - or no reminders exist for this diagnosis (total_steps === 0)
  const showProgress = progress != null && progress.total_steps > 0;
  const cycleComplete =
    progress != null && progress.completed_steps >= progress.total_steps;
  // "Next spray in X days" — derive from next_scheduled_at if the
  // cron hasn't yet computed it, fall back to interval_days for the
  // first-step case (where completed=0 and scheduled_at is far in
  // the future).
  const daysToNext = (() => {
    if (!progress?.next_scheduled_at) return null;
    const ms = new Date(progress.next_scheduled_at).getTime() - Date.now();
    if (Number.isNaN(ms)) return null;
    return Math.max(0, Math.ceil(ms / (24 * 60 * 60 * 1000)));
  })();

  // Gradient changes with severity — gentle green for medium, warmer
  // for high/critical. Keeps the "this matters" signal without being
  // alarmist.
  const gradientByLevel = {
    medium: 'from-leaf-500 via-leaf-600 to-leaf-800',
    high: 'from-leaf-500 via-saffron-600 to-saffron-700',
    critical: 'from-saffron-500 via-saffron-700 to-soil-700',
  };
  const gradient =
    gradientByLevel[severityKey as keyof typeof gradientByLevel] ??
    gradientByLevel.medium;

  return (
    <Link
      to={`/result/${diag.diagnostic_id}`}
      className={`relative block overflow-hidden rounded-2xl bg-gradient-to-br ${gradient} text-white shadow-card transition-shadow hover:shadow-hover`}
    >
      {/* Background emoji — large, off-axis, slightly transparent so it
          reads as art rather than a sticker. */}
      <span
        aria-hidden
        className="pointer-events-none absolute -right-6 -top-6 select-none text-[180px] leading-none opacity-90 rotate-6"
        style={{ filter: 'drop-shadow(0 8px 20px rgba(0,0,0,0.18))' }}
      >
        {emoji}
      </span>

      <div className="relative p-5">
        <span className="inline-block rounded-full border border-white/25 bg-white/15 px-2.5 py-1 text-2xs font-semibold uppercase tracking-wider backdrop-blur">
          ⚠ {t('home.hero_active_eyebrow')}
        </span>

        <h2 className="mt-3 font-display text-3xl font-bold leading-tight">
          {diag.plant_classification ?? t('history.unknown_plant')}
        </h2>
        <p className="mt-1 text-sm font-medium text-white/90">
          {diag.disease_name ?? '—'}
        </p>

        <div className="mt-3 flex flex-wrap gap-3 text-xs text-white/85">
          <span className="flex items-center gap-1">
            <AlertTriangle className="h-3 w-3" />
            {t(`result.severity_${severityKey}`, severityKey)}
          </span>
          <span>· {formatRelativeShort(diag.add_date)}</span>
        </div>

        {/* Treatment-cycle progress. Hidden when no reminders exist
            (low-severity, viral / abiotic / weed, or user opted out)
            so the active-hero stays compact for those diagnoses. */}
        {showProgress && progress != null ? (
          <div className="mt-4 rounded-xl bg-white/10 px-3 py-2.5 backdrop-blur">
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-white/95">
                {cycleComplete
                  ? t('home.hero_treatment_complete')
                  : t('home.hero_treatment_step', {
                      current: progress.current_step,
                      total: progress.total_steps,
                    })}
              </span>
              <span className="text-2xs text-white/85">
                {cycleComplete
                  ? null
                  : daysToNext === 0
                    ? t('home.hero_treatment_due_today')
                    : daysToNext != null
                      ? t('home.hero_treatment_next_in', { count: daysToNext })
                      : null}
              </span>
            </div>
            {/* 3-segment progress bar. Filled segment = sent reminder;
                ring-outlined = current step; faint = upcoming. Pure
                CSS, no canvas, looks crisp at any DPR. */}
            <div className="mt-2 flex gap-1.5">
              {Array.from({ length: progress.total_steps }, (_, i) => {
                const stepIdx = i + 1;
                const isDone = stepIdx <= progress.completed_steps;
                const isCurrent =
                  !cycleComplete && stepIdx === progress.current_step;
                return (
                  <span
                    key={stepIdx}
                    className={
                      'h-1.5 flex-1 rounded-full transition-colors ' +
                      (isDone
                        ? 'bg-white'
                        : isCurrent
                          ? 'bg-white/70 ring-2 ring-white/30'
                          : 'bg-white/25')
                    }
                  />
                );
              })}
            </div>
          </div>
        ) : null}

        <div className="mt-4 grid grid-cols-3 gap-2">
          <span className="rounded-lg bg-white px-2 py-2 text-center text-xs font-semibold text-leaf-800 shadow-card">
            {t('home.hero_action_view')}
          </span>
          <span className="rounded-lg border border-white/30 bg-white/15 px-2 py-2 text-center text-xs font-semibold backdrop-blur">
            {t('home.hero_action_scan_again')}
          </span>
          <span className="rounded-lg border border-white/30 bg-white/15 px-2 py-2 text-center text-xs font-semibold backdrop-blur">
            {t('home.hero_action_history')}
          </span>
        </div>
      </div>
    </Link>
  );
}

function HealthyHero({ latest }: { latest: DiagnosticRead | null }) {
  const { t } = useTranslation();
  const emoji = cropEmoji(latest?.plant_classification) ?? '🌿';

  return (
    <Link
      to="/scan"
      className="relative block overflow-hidden rounded-2xl bg-gradient-to-br from-leaf-50 via-white to-leaf-100 p-5 shadow-card transition-shadow hover:shadow-hover"
    >
      <span
        aria-hidden
        className="pointer-events-none absolute -right-4 -bottom-6 select-none text-[160px] leading-none opacity-30 rotate-6"
      >
        {emoji}
      </span>
      <div className="relative">
        <span className="inline-block rounded-full bg-leaf-100 px-2.5 py-1 text-2xs font-semibold uppercase tracking-wider text-leaf-700">
          ✓ {t('home.hero_healthy_eyebrow')}
        </span>
        <h2 className="mt-3 font-display text-2xl font-semibold text-ink-800">
          {t('home.hero_healthy_title')}
        </h2>
        <p className="mt-1 text-sm text-ink-600">
          {t('home.hero_healthy_subtitle')}
        </p>
        <span className="mt-4 inline-flex items-center gap-2 rounded-lg bg-leaf-600 px-4 py-2.5 text-sm font-semibold text-white shadow-card">
          <Camera className="h-4 w-4" />
          {t('home.hero_action_quick_scan')}
        </span>
      </div>
    </Link>
  );
}

function EmptyHero({ loading }: { loading: boolean }) {
  const { t } = useTranslation();
  return (
    <Link
      to="/scan"
      className="group relative block overflow-hidden rounded-2xl bg-gradient-to-br from-leaf-600 to-leaf-800 p-5 text-white shadow-card transition-shadow hover:shadow-hover"
    >
      <span
        aria-hidden
        className="pointer-events-none absolute -right-4 -bottom-6 select-none text-[140px] leading-none opacity-30"
      >
        🌱
      </span>
      <div className="relative flex items-center gap-4">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-white/15 backdrop-blur">
          <Camera className="h-6 w-6" strokeWidth={2.25} />
        </div>
        <div className="flex-1">
          <h3 className="font-display text-lg font-semibold">
            {loading ? t('common.loading') : t('home.hero_empty_title')}
          </h3>
          <p className="text-sm text-white/85">{t('home.hero_empty_subtitle')}</p>
        </div>
        <ChevronRight className="h-5 w-5 shrink-0 opacity-80 transition-transform group-hover:translate-x-0.5" />
      </div>
    </Link>
  );
}

/* ============================================================
   In your area — outbreak alert
   ============================================================
   The panel is intentionally borrowed from Direction B in the
   home-mockups comparison. Saffron accent (warning, not alarm),
   compact, one-liner copy with the report count + disease label
   embedded so the farmer can decide in one glance whether to act. */
function InYourAreaPanel({
  outbreak,
  pincode,
}: {
  outbreak: OutbreakItem;
  pincode: string;
}) {
  const { t } = useTranslation();
  return (
    <section className="mt-5">
      <div className="mb-2 flex items-baseline justify-between">
        <h3 className="section-heading mb-0">
          {t('home.area_section', { pincode })}
        </h3>
      </div>
      <div className="card-saffron flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-saffron-200/60 text-saffron-700">
          <AlertTriangle className="h-4.5 w-4.5" />
        </div>
        <div className="flex-1 text-sm">
          <p className="font-medium text-saffron-800">
            {t('home.area_template', {
              count: outbreak.report_count,
              disease: t(
                `infection_type.${outbreak.infection_type}`,
                outbreak.infection_type,
              ),
            })}
          </p>
          <p className="mt-1 text-xs text-saffron-700">
            {t('home.area_help')}
          </p>
        </div>
      </div>
    </section>
  );
}

/* ============================================================
   Crop chips
   ============================================================ */

function CropChip({ name }: { name: string }) {
  const emoji = cropEmoji(name);
  return (
    <span className="flex shrink-0 items-center gap-1.5 rounded-full border border-leaf-100 bg-leaf-50 px-3 py-1.5 text-xs font-medium text-leaf-800">
      {emoji ? <span>{emoji}</span> : <Leaf className="h-3 w-3 text-leaf-600" />}
      <span>{name}</span>
    </span>
  );
}

/* ============================================================
   Recent scans
   ============================================================ */

function ScanCard({ diag }: { diag: DiagnosticRead }) {
  const { t } = useTranslation();
  const emoji = cropEmoji(diag.plant_classification) ?? '🌿';

  // Severity-based thumbnail gradient; same vocabulary as ActiveHero.
  const severity = (diag.severity ?? 'medium').toLowerCase();
  const isRejected = !!diag.rejection_reason;
  const thumbGradient = isRejected
    ? 'from-ink-100 to-ink-200'
    : severity === 'critical'
      ? 'from-red-100 to-red-300'
      : severity === 'high'
        ? 'from-saffron-100 to-saffron-300'
        : severity === 'medium'
          ? 'from-saffron-50 to-leaf-100'
          : 'from-leaf-100 to-leaf-200';

  // Chip — one line, severity or healthy or rejected.
  let chipText = '—';
  let chipClass = 'bg-ink-100 text-ink-700';
  if (isRejected) {
    chipText = t('home.scan_chip_unclear', 'Unclear');
    chipClass = 'bg-ink-100 text-ink-600';
  } else if (!diag.infection_type || diag.infection_type === 'unknown') {
    chipText = t('home.scan_chip_healthy', 'Healthy');
    chipClass = 'bg-success-soft text-success';
  } else if (severity === 'critical' || severity === 'high') {
    chipText = t(`infection_type.${diag.infection_type}`, diag.infection_type);
    chipClass = 'bg-red-50 text-red-700';
  } else {
    chipText = t(`infection_type.${diag.infection_type}`, diag.infection_type);
    chipClass = 'bg-saffron-50 text-saffron-700';
  }

  return (
    <Link
      to={`/result/${diag.diagnostic_id}`}
      className="block w-[140px] shrink-0 overflow-hidden rounded-xl bg-white shadow-card transition-shadow hover:shadow-hover"
    >
      <div
        className={`flex h-24 items-center justify-center bg-gradient-to-br ${thumbGradient} text-4xl`}
      >
        {emoji}
      </div>
      <div className="p-2.5">
        <p className="truncate text-sm font-semibold text-ink-800">
          {diag.plant_classification ?? t('history.unknown_plant')}
        </p>
        <p className="mt-0.5 text-2xs text-ink-500">
          {formatRelativeShort(diag.add_date)}
        </p>
        <span className={`mt-1.5 inline-block rounded px-1.5 py-0.5 text-2xs font-semibold ${chipClass}`}>
          {chipText}
        </span>
      </div>
    </Link>
  );
}

function RecentSkeleton() {
  return (
    <div className="-mx-4 px-4 flex gap-3 overflow-hidden">
      {[0, 1, 2].map((i) => (
        <div key={i} className="w-[140px] shrink-0 overflow-hidden rounded-xl bg-white shadow-card">
          <div className="skeleton h-24" />
          <div className="space-y-1.5 p-2.5">
            <div className="skeleton h-3 w-3/4 rounded" />
            <div className="skeleton h-2.5 w-1/2 rounded" />
          </div>
        </div>
      ))}
    </div>
  );
}

/* ============================================================
   Tiny relative-time formatter — handful-of-days resolution.
   ============================================================ */

function formatRelativeShort(iso: string): string {
  const dt = new Date(iso).getTime();
  if (Number.isNaN(dt)) return '—';
  const days = Math.floor((Date.now() - dt) / (24 * 60 * 60 * 1000));
  if (days === 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 7) return `${days}d ago`;
  if (days < 30) return `${Math.floor(days / 7)}w ago`;
  return `${Math.floor(days / 30)}mo ago`;
}
