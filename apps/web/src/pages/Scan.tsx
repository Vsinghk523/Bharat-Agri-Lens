import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { api } from '@/lib/api';
import { useRequireAuth } from '@/lib/auth';
import { pickImage } from '@/lib/camera';
import { isNativePlatform } from '@/lib/platform';

export default function Scan() {
  useRequireAuth();
  const { t, i18n } = useTranslation();
  const nav = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const native = isNativePlatform();

  async function chooseFile(source: 'camera' | 'gallery' | 'prompt') {
    setError(null);
    try {
      const picked = await pickImage({ source, filename: 'scan.jpg' });
      setFile(picked);
    } catch (err) {
      // User-cancel is the dominant case here; only surface the message
      // if it's actually unexpected.
      if (err instanceof Error && !/cancel/i.test(err.message)) {
        setError(err.message);
      }
    }
  }

  async function submit() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      // Stream the file through the API (server-side PUT to object storage).
      // Avoids the browser-PUT-to-bucket flow, which doesn't work on object
      // stores like Railway T3 that don't expose CORS configuration.
      const image = await api.uploads.direct(file, file.name.slice(0, 50));
      const diag = await api.diagnostics.create({
        image_id: image.image_id,
        language: i18n.resolvedLanguage ?? 'en-IN',
      });
      nav(`/result/${diag.diagnostic_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scan failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mx-auto max-w-lg py-8">
      <div className="card space-y-4">
        <h2 className="text-2xl font-semibold text-leaf-700">{t('scan.title')}</h2>
        <p className="text-sm text-soil-500">{t('scan.hint')}</p>

        {/*
          On Capacitor (Android / iOS) we expose two explicit choices
          — Take photo and Pick from gallery — so the user gets the
          full-resolution native camera vs. the gallery picker. On
          plain web we fall back to a single button that triggers a
          regular file picker (with a "use camera" hint on mobile
          browsers); explicit camera vs gallery split there isn't
          reliably supported across browsers, so one button is less
          confusing.
        */}
        {native ? (
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => chooseFile('camera')}
              className="btn-secondary"
            >
              {t('scan.take_photo', 'Take photo')}
            </button>
            <button
              type="button"
              onClick={() => chooseFile('gallery')}
              className="btn-secondary"
            >
              {t('scan.choose_from_gallery', 'Choose from gallery')}
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => chooseFile('prompt')}
            className="btn-secondary w-full"
          >
            {t('scan.choose_file', 'Choose image')}
          </button>
        )}

        {file && (
          <p className="text-xs text-soil-500">
            {file.name} · {(file.size / 1024).toFixed(0)} KB
          </p>
        )}
        <button
          type="button"
          disabled={!file || busy}
          onClick={submit}
          className="btn-primary w-full"
        >
          {busy ? t('scan.analyzing') : t('scan.analyze')}
        </button>
        {error && <p className="text-sm text-red-600">{error}</p>}
      </div>
    </section>
  );
}
