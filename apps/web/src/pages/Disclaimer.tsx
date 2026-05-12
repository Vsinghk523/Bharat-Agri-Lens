import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

export default function Disclaimer() {
  const { t } = useTranslation();
  const nav = useNavigate();
  return (
    <section className="mx-auto max-w-xl py-12">
      <div className="card space-y-4">
        <h2 className="text-2xl font-semibold text-leaf-700">{t('disclaimer.title')}</h2>
        <p className="text-sm text-soil-500">{t('disclaimer.body_ai')}</p>
        <p className="text-sm text-soil-500">{t('disclaimer.body_pii')}</p>
        <button
          type="button"
          onClick={() => {
            localStorage.setItem('bal_consent_v1', new Date().toISOString());
            nav('/home');
          }}
          className="btn-primary w-full"
        >
          {t('disclaimer.accept')}
        </button>
      </div>
    </section>
  );
}
