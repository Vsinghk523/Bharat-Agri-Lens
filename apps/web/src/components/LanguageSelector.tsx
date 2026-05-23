import { useTranslation } from 'react-i18next';
import { Globe } from 'lucide-react';
import { supportedLanguages } from '@bal/i18n';

/**
 * Language picker.
 *
 * Two visual modes:
 * - ``variant="compact"`` (default): chip-style with a globe icon and
 *   the current language's native label. Used in app bars where space
 *   is at a premium.
 * - ``variant="full"``: full-width row used inside profile/settings
 *   where the user is intentionally choosing a language.
 *
 * Either way we still use a native ``<select>`` for accessibility +
 * keyboard / screen-reader correctness; only the visible styling
 * changes.
 */
export interface LanguageSelectorProps {
  variant?: 'compact' | 'full';
}

export default function LanguageSelector({ variant = 'compact' }: LanguageSelectorProps) {
  const { i18n } = useTranslation();
  const current = supportedLanguages.find((l) => l.code === i18n.resolvedLanguage);

  if (variant === 'compact') {
    return (
      <label className="relative inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-full border border-ink-200 bg-white pl-2.5 pr-3 text-sm text-ink-700 transition-colors hover:border-leaf-300 hover:bg-leaf-50">
        <Globe className="h-4 w-4 text-ink-500" />
        <span className="truncate font-medium">{current?.label ?? 'English'}</span>
        <select
          aria-label="Language"
          value={i18n.resolvedLanguage}
          onChange={(e) => i18n.changeLanguage(e.target.value)}
          className="absolute inset-0 cursor-pointer opacity-0"
        >
          {supportedLanguages.map((l) => (
            <option key={l.code} value={l.code}>
              {l.label}
            </option>
          ))}
        </select>
      </label>
    );
  }

  return (
    <label className="block">
      <span className="label">Language</span>
      <select
        aria-label="Language"
        value={i18n.resolvedLanguage}
        onChange={(e) => i18n.changeLanguage(e.target.value)}
        className="input"
      >
        {supportedLanguages.map((l) => (
          <option key={l.code} value={l.code}>
            {l.label}
          </option>
        ))}
      </select>
    </label>
  );
}
