import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowRight, Camera, Globe, Leaf, ShieldCheck } from 'lucide-react';
import LanguageSelector from '@/components/LanguageSelector';

/**
 * Landing screen — first impression for unauthenticated visitors.
 *
 * Three-feature pitch under the hero, then a primary CTA. Designed to
 * fit cleanly in an Android WebView's safe area, so the visible viewport
 * on most phones renders the hero + CTAs without scrolling.
 */
export default function Landing() {
  const { t } = useTranslation();

  return (
    <div className="min-h-screen bg-gradient-to-b from-leaf-50 via-white to-ink-50">
      {/* Top utility bar — language picker only */}
      <div className="flex items-center justify-end px-4 pt-safe">
        <div className="py-3">
          <LanguageSelector />
        </div>
      </div>

      <main className="mx-auto flex max-w-md flex-col px-6 pb-10 pt-4 animate-fade-in">
        {/* Brand mark */}
        <div className="mb-8 flex items-center gap-2">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-leaf-600 text-white shadow-card">
            <Leaf className="h-5 w-5" strokeWidth={2.25} />
          </span>
          <span className="font-display text-lg font-semibold text-ink-800">
            {t('landing.title')}
          </span>
        </div>

        {/* Hero */}
        <h1 className="font-display text-4xl font-semibold leading-tight tracking-tight text-ink-800">
          {t('landing.tagline')}
        </h1>
        <p className="mt-3 text-base text-ink-600">{t('landing.subtitle')}</p>

        {/* Features */}
        <ul className="mt-8 space-y-3">
          <FeatureRow
            icon={<Camera className="h-4 w-4" />}
            title={t('landing.feature_1_title')}
            body={t('landing.feature_1_body')}
          />
          <FeatureRow
            icon={<ShieldCheck className="h-4 w-4" />}
            title={t('landing.feature_2_title')}
            body={t('landing.feature_2_body')}
          />
          <FeatureRow
            icon={<Globe className="h-4 w-4" />}
            title={t('landing.feature_3_title')}
            body={t('landing.feature_3_body')}
          />
        </ul>

        {/* CTAs */}
        <div className="mt-10 space-y-3">
          <Link to="/login" className="btn-primary btn-lg w-full">
            {t('landing.cta_login')}
            <ArrowRight className="h-4 w-4" />
          </Link>
          <p className="text-center text-xs text-ink-500">
            {t('footer.tagline')}
          </p>
        </div>
      </main>
    </div>
  );
}

function FeatureRow({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <li className="flex items-start gap-3">
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-leaf-100 text-leaf-700">
        {icon}
      </span>
      <div>
        <p className="text-sm font-semibold text-ink-800">{title}</p>
        <p className="text-xs text-ink-500">{body}</p>
      </div>
    </li>
  );
}
