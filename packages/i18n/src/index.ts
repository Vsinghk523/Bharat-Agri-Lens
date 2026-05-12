import en from '../locales/en.json';
import hi from '../locales/hi.json';
import mr from '../locales/mr.json';
import ta from '../locales/ta.json';
import te from '../locales/te.json';
import bn from '../locales/bn.json';
import gu from '../locales/gu.json';
import kn from '../locales/kn.json';
import ml from '../locales/ml.json';
import pa from '../locales/pa.json';

export interface SupportedLanguage {
  code: string;
  label: string;
  bcp47: string;
}

export const supportedLanguages: SupportedLanguage[] = [
  { code: 'en', label: 'English', bcp47: 'en-IN' },
  { code: 'hi', label: 'हिन्दी', bcp47: 'hi-IN' },
  { code: 'mr', label: 'मराठी', bcp47: 'mr-IN' },
  { code: 'ta', label: 'தமிழ்', bcp47: 'ta-IN' },
  { code: 'te', label: 'తెలుగు', bcp47: 'te-IN' },
  { code: 'bn', label: 'বাংলা', bcp47: 'bn-IN' },
  { code: 'gu', label: 'ગુજરાતી', bcp47: 'gu-IN' },
  { code: 'kn', label: 'ಕನ್ನಡ', bcp47: 'kn-IN' },
  { code: 'ml', label: 'മലയാളം', bcp47: 'ml-IN' },
  { code: 'pa', label: 'ਪੰਜਾਬੀ', bcp47: 'pa-IN' },
];

export const resources = {
  en: { translation: en },
  hi: { translation: hi },
  mr: { translation: mr },
  ta: { translation: ta },
  te: { translation: te },
  bn: { translation: bn },
  gu: { translation: gu },
  kn: { translation: kn },
  ml: { translation: ml },
  pa: { translation: pa },
} as const;

export type TranslationKey = keyof typeof en;
