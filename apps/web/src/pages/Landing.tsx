import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

export default function Landing() {
  const { t } = useTranslation();
  return (
    <section className="flex flex-col items-center gap-6 py-16 text-center">
      <h1 className="text-4xl font-bold text-leaf-700">{t('landing.title')}</h1>
      <p className="max-w-xl text-soil-500">{t('landing.subtitle')}</p>
      <div className="flex gap-3">
        <Link to="/login" className="btn-primary">
          {t('landing.cta_login')}
        </Link>
        <Link to="/scan" className="btn-secondary">
          {t('landing.cta_scan')}
        </Link>
      </div>
    </section>
  );
}
