import { Link, Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import LanguageSelector from './LanguageSelector';

export default function Layout() {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-leaf-100 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <Link to="/" className="text-lg font-semibold text-leaf-700">
            BharatAgriLens
          </Link>
          <nav className="flex items-center gap-4 text-sm">
            <Link to="/scan" className="hover:text-leaf-700">
              {t('nav.scan')}
            </Link>
            <Link to="/chat" className="hover:text-leaf-700">
              {t('nav.chat')}
            </Link>
            <Link to="/history" className="hover:text-leaf-700">
              {t('nav.history')}
            </Link>
            <LanguageSelector />
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">
        <Outlet />
      </main>
      <footer className="border-t border-leaf-100 bg-white py-3 text-center text-xs text-soil-500">
        © {new Date().getFullYear()} BharatAgriLens · {t('footer.tagline')}
      </footer>
    </div>
  );
}
