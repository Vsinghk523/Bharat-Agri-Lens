import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Camera, Image as ImageIcon, Loader2, RefreshCw, Sun, Focus, Leaf } from 'lucide-react';
import { api } from '@/lib/api';
import { useRequireAuth } from '@/lib/auth';
import { pickImage } from '@/lib/camera';
import { isNativePlatform } from '@/lib/platform';
import AppBar from '@/components/ui/AppBar';

/**
 * Scan flow — choose / capture an image, preview it, click Analyze.
 *
 * Native platforms get two explicit buttons (camera vs gallery). Web
 * gets one single picker since most browsers don't reliably split the
 * two anyway. After a file is selected we show a large preview with
 * a "Replace" affordance and surface the actual Analyze CTA.
 */
export default function Scan() {
  useRequireAuth();
  const { t, i18n } = useTranslation();
  const nav = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const native = isNativePlatform();

  async function chooseFile(source: 'camera' | 'gallery' | 'prompt') {
    setError(null);
    try {
      const picked = await pickImage({ source, filename: 'scan.jpg' });
      setFile(picked);
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      setPreviewUrl(URL.createObjectURL(picked));
    } catch (err) {
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
      const image = await api.uploads.direct(file, file.name.slice(0, 50));
      const diag = await api.diagnostics.create({
        image_id: image.image_id,
        language: i18n.resolvedLanguage ?? 'en-IN',
      });
      nav(`/result/${diag.diagnostic_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.error'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <AppBar title={t('scan.title')} />

      <div className="mx-auto max-w-2xl px-4 py-5 animate-fade-in">
        {!file ? (
          <>
            {/* Hint card with three quick tips */}
            <div className="card mb-4">
              <h2 className="font-display text-base font-semibold text-ink-800">
                {t('scan.hint')}
              </h2>
              <ul className="mt-3 space-y-2">
                <TipRow icon={<Sun className="h-4 w-4" />} text={t('scan.tip_lighting')} />
                <TipRow icon={<Focus className="h-4 w-4" />} text={t('scan.tip_focus')} />
                <TipRow icon={<Leaf className="h-4 w-4" />} text={t('scan.tip_one_plant')} />
              </ul>
            </div>

            {/* CTA(s) */}
            {native ? (
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => chooseFile('camera')}
                  className="btn-primary btn-lg flex-col py-6"
                >
                  <Camera className="h-7 w-7" />
                  <span>{t('scan.take_photo')}</span>
                </button>
                <button
                  type="button"
                  onClick={() => chooseFile('gallery')}
                  className="btn-secondary btn-lg flex-col py-6"
                >
                  <ImageIcon className="h-7 w-7" />
                  <span>{t('scan.choose_from_gallery')}</span>
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => chooseFile('prompt')}
                className="btn-primary btn-lg w-full"
              >
                <ImageIcon className="h-5 w-5" />
                {t('scan.choose_file')}
              </button>
            )}
          </>
        ) : (
          <>
            {/* Preview */}
            <div className="card-flat overflow-hidden p-0">
              <img
                src={previewUrl ?? ''}
                alt={file.name}
                className="block aspect-square w-full object-cover"
              />
              <div className="flex items-center justify-between px-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-ink-800">{file.name}</p>
                  <p className="text-xs text-ink-500">{(file.size / 1024).toFixed(0)} KB</p>
                </div>
                <button
                  type="button"
                  onClick={() => chooseFile(native ? 'camera' : 'prompt')}
                  className="btn-ghost btn-sm"
                  disabled={busy}
                >
                  <RefreshCw className="h-4 w-4" />
                  {t('scan.retake')}
                </button>
              </div>
            </div>

            <p className="mt-3 text-center text-xs text-ink-500">
              {t('scan.preview_hint')}
            </p>

            <button
              type="button"
              disabled={busy}
              onClick={submit}
              className="btn-primary btn-lg mt-4 w-full"
            >
              {busy ? (
                <>
                  <Loader2 className="h-5 w-5 animate-spin" />
                  {t('scan.analyzing')}
                </>
              ) : (
                t('scan.analyze')
              )}
            </button>
          </>
        )}

        {error ? (
          <div className="mt-4 rounded-lg border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger">
            {error}
          </div>
        ) : null}
      </div>
    </>
  );
}

function TipRow({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <li className="flex items-center gap-2.5 text-sm text-ink-600">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-leaf-100 text-leaf-700">
        {icon}
      </span>
      <span>{text}</span>
    </li>
  );
}
