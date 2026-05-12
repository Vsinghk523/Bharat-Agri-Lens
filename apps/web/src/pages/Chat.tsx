import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '@/lib/api';
import { useRequireAuth } from '@/lib/auth';
import MicButton from '@/components/MicButton';

interface Message {
  role: 'user' | 'assistant';
  text: string;
}

export default function Chat() {
  useRequireAuth();
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage
    ? `${i18n.resolvedLanguage}-IN`
    : 'en-IN';
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [playingIdx, setPlayingIdx] = useState<number | null>(null);

  function send(text?: string) {
    const body = (text ?? input).trim();
    if (!body) return;
    setMessages((m) => [
      ...m,
      { role: 'user', text: body },
      { role: 'assistant', text: t('chat.stub_reply') },
    ]);
    setInput('');
  }

  async function playTts(text: string, idx: number) {
    setPlayingIdx(idx);
    try {
      const resp = await api.voice.tts({ text, language });
      const blob = base64ToBlob(resp.audio_b64, resp.mime_type);
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.onended = () => {
        URL.revokeObjectURL(url);
        setPlayingIdx((cur) => (cur === idx ? null : cur));
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        setPlayingIdx((cur) => (cur === idx ? null : cur));
      };
      await audio.play();
    } catch {
      setPlayingIdx((cur) => (cur === idx ? null : cur));
    }
  }

  return (
    <section className="flex h-[70vh] flex-col gap-3 py-4">
      <h2 className="text-xl font-semibold text-leaf-700">{t('chat.title')}</h2>
      <div className="card flex-1 overflow-y-auto">
        {messages.length === 0 && (
          <p className="text-sm text-soil-500">{t('chat.start_hint')}</p>
        )}
        <ul className="space-y-2">
          {messages.map((m, i) => (
            <li
              key={i}
              className={
                m.role === 'user'
                  ? 'ml-auto flex max-w-xs items-start gap-2 rounded bg-leaf-600 px-3 py-2 text-sm text-white'
                  : 'mr-auto flex max-w-xs items-start gap-2 rounded bg-leaf-100 px-3 py-2 text-sm text-soil-900'
              }
            >
              <span className="flex-1">{m.text}</span>
              {m.role === 'assistant' && (
                <button
                  type="button"
                  aria-label={t('chat.tts_play')}
                  onClick={() => playTts(m.text, i)}
                  disabled={playingIdx === i}
                  className="text-leaf-700 hover:text-leaf-900 disabled:opacity-50"
                  title={t('chat.tts_play')}
                >
                  {playingIdx === i ? '⏵' : '🔊'}
                </button>
              )}
            </li>
          ))}
        </ul>
      </div>
      <div className="flex items-center gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          placeholder={t('chat.input_ph')}
          className="flex-1 rounded border px-3 py-2"
        />
        <MicButton language={language} onTranscript={(text) => send(text)} />
        <button type="button" onClick={() => send()} className="btn-primary">
          {t('chat.send')}
        </button>
      </div>
    </section>
  );
}

function base64ToBlob(b64: string, mime: string): Blob {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new Blob([bytes], { type: mime });
}
