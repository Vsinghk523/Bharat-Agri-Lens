import { Link, Outlet, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import LanguageSelector from './LanguageSelector';
import { clearAuth, getAccessToken, getUserId, useRole } from '@/lib/auth';

export default function Layout() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const isAuthed = !!getAccessToken();
  const userId = getUserId();
  const role = useRole();
  const isAdminUser = isAuthed && role === 'admin';

  function logout() {
    clearAuth();
    nav('/login', { replace: true });
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-leaf-100 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <Link to={isAuthed ? '/home' : '/'} className="text-lg font-semibold text-leaf-700">
            BharatAgriLens
          </Link>
          <nav className="flex items-center gap-3 text-sm">
            {isAuthed && (
              <>
                <Link to="/scan" className="hover:text-leaf-700">
                  {t('nav.scan')}
                </Link>
                <Link to="/chat" className="hover:text-leaf-700">
                  {t('nav.chat')}
                </Link>
                <Link to="/history" className="hover:text-leaf-700">
                  {t('nav.history')}
                </Link>
                {isAdminUser && (
                  <Link
                    to="/admin/labelling-queue"
                    className="rounded bg-amber-50 px-2 py-0.5 text-amber-900 hover:bg-amber-100"
                  >
                    {t('nav.admin')}
                  </Link>
                )}
              </>
            )}
            <LanguageSelector />
            {isAuthed ? (
              <>
                <span
                  title={userId ?? ''}
                  className="hidden text-xs text-soil-500 sm:inline"
                >
                  {userId}
                </span>
                <button
                  type="button"
                  onClick={logout}
                  className="rounded border border-leaf-100 px-2 py-1 text-xs text-soil-900 hover:bg-leaf-100"
                >
                  {t('nav.logout')}
                </button>
              </>
            ) : (
              <Link
                to="/login"
                className="rounded border border-leaf-100 px-2 py-1 text-xs text-soil-900 hover:bg-leaf-100"
              >
                {t('nav.login')}
              </Link>
            )}
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
