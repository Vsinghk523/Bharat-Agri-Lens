import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { api } from '@/lib/api';
import { useRequireAuth } from '@/lib/auth';

export default function Scan() {
  useRequireAuth();
  const { t, i18n } = useTranslation();
  const nav = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const presign = await api.uploads.presign({
        image_name: file.name.slice(0, 50),
        mime_type: file.type,
        size_bytes: file.size,
      });
      // Content-Type MUST match what the API used when signing, otherwise
      // S3 rejects the PUT with SignatureDoesNotMatch.
      const putResp = await fetch(presign.upload_url, {
        method: 'PUT',
        headers: { 'Content-Type': file.type },
        body: file,
      });
      if (!putResp.ok) {
        throw new Error(`Upload failed: ${putResp.status} ${putResp.statusText}`);
      }
      const diag = await api.diagnostics.create({
        image_id: presign.image_id,
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
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="block w-full text-sm"
        />
        {file && (
          <p className="text-xs text-soil-500">
            {file.name} · {(file.size / 1024).toFixed(0)} KB
          </p>
        )}
        <button type="button" disabled={!file || busy} onClick={submit} className="btn-primary w-full">
          {busy ? t('scan.analyzing') : t('scan.analyze')}
        </button>
        {error && <p className="text-sm text-red-600">{error}</p>}
      </div>
    </section>
  );
}
