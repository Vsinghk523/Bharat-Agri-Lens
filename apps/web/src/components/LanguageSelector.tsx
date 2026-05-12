import { useTranslation } from 'react-i18next';
import { supportedLanguages } from '@bal/i18n';

export default function LanguageSelector() {
  const { i18n } = useTranslation();
  return (
    <select
      aria-label="Language"
      value={i18n.resolvedLanguage}
      onChange={(e) => i18n.changeLanguage(e.target.value)}
      className="rounded border border-leaf-100 bg-white px-2 py-1 text-sm"
    >
      {supportedLanguages.map((l) => (
        <option key={l.code} value={l.code}>
          {l.label}
        </option>
      ))}
    </select>
  );
}
