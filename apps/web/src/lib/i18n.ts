import i18n from 'i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import { initReactI18next } from 'react-i18next';
import { resources, supportedLanguages } from '@bal/i18n';

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'en',
    supportedLngs: supportedLanguages.map((l) => l.code),
    // i18next 4+ defaults to CLDR plural keys (_one / _other). All
    // our locale files use the legacy v3 convention (`key` for
    // singular, `key_plural` for everything else), so pin that
    // behaviour. Avoids having to maintain CLDR-correct plural
    // forms across 10 Indic languages for one pluralised string.
    compatibilityJSON: 'v3',
    interpolation: { escapeValue: false },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
    },
  });

export default i18n;
