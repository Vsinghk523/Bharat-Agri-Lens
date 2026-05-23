import { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';

/**
 * Top app bar — full-bleed, sticky, used on every authenticated screen.
 *
 * Three slots: back/leading icon · title · trailing actions. Designed
 * for the bottom-tab layout where the only "navigation chrome" up top
 * is contextual (back arrow on detail screens, brand on tab roots).
 */
export interface AppBarProps {
  /**
   * Page title. Pass the static label or an already-translated string;
   * we don't call i18n here so callers stay flexible.
   */
  title?: ReactNode;
  /** Optional small subtitle line under the title. */
  subtitle?: ReactNode;
  /**
   * Show a back arrow that navigates(-1) when clicked. Use on detail
   * screens (result, individual notification, etc.). Leave false on
   * tab-root screens (home, history, profile).
   */
  showBack?: boolean;
  /** Override the back action — defaults to ``navigate(-1)``. */
  onBack?: () => void;
  /** Trailing slot — typically icon buttons (notifications, more). */
  trailing?: ReactNode;
  /**
   * When true, the bar is transparent over the page content. Used on
   * the Result hero where the photo bleeds behind the bar. */
  transparent?: boolean;
}

export default function AppBar({
  title,
  subtitle,
  showBack,
  onBack,
  trailing,
  transparent,
}: AppBarProps) {
  const navigate = useNavigate();

  return (
    <header
      className={
        transparent
          ? 'sticky top-0 z-30 flex h-14 items-center gap-2 px-3 pt-safe'
          : 'sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-ink-100 bg-white/95 px-3 pt-safe backdrop-blur supports-[backdrop-filter]:bg-white/80'
      }
    >
      {showBack ? (
        <button
          type="button"
          onClick={() => (onBack ? onBack() : navigate(-1))}
          aria-label="Back"
          className="btn-ghost btn-icon"
        >
          <ChevronLeft className="h-5 w-5" />
        </button>
      ) : (
        <div className="w-2" />
      )}

      <div className="min-w-0 flex-1">
        {title ? (
          <h1 className="truncate font-display text-base font-semibold text-ink-800">
            {title}
          </h1>
        ) : null}
        {subtitle ? (
          <p className="truncate text-2xs text-ink-500">{subtitle}</p>
        ) : null}
      </div>

      {trailing ? <div className="flex items-center gap-1">{trailing}</div> : null}
    </header>
  );
}
