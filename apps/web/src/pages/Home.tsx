import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useRequireAuth } from '@/lib/auth';

export default function Home() {
  useRequireAuth();
  const { t } = useTranslation();
  const tiles = [
    { to: '/scan', key: 'home.scan_plant' },
    { to: '/scan', key: 'home.upload_photo' },
    { to: '/chat', key: 'home.ai_chat' },
    { to: '/history', key: 'home.history' },
  ];
  return (
    <section className="grid grid-cols-1 gap-4 py-6 sm:grid-cols-2">
      {tiles.map((tile) => (
        <Link key={tile.key} to={tile.to} className="card hover:bg-leaf-100">
          <h3 className="text-lg font-medium text-leaf-700">{t(tile.key)}</h3>
          <p className="mt-1 text-sm text-soil-500">{t(`${tile.key}_hint`)}</p>
        </Link>
      ))}
    </section>
  );
}
