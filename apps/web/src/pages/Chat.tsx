import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '@/lib/api';
import { useRequireAuth } from '@/lib/auth';
import MicButton from '@/components/MicButton';

interface Message {
  role: 'user' | 'assistant';
  text: string;
  error?: boolean;
}

export default function Chat() {
  useRequireAuth();
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage
    ? `${i18n.resolvedLanguage}-IN`
    : 'en-IN';
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [playingIdx, setPlayingIdx] = useState<number | null>(null);

  async function send(text?: string) {
    const body = (text ?? input).trim();
    if (!body || sending) return;
    setInput('');
    setSending(true);
    // Optimistic user bubble.
    setMessages((m) => [...m, { role: 'user', text: body }]);
    try {
      const exchange = await api.chat.postMessage({
        session_id: sessionId ?? undefined,
        language,
        content_text: body,
      });
      setSessionId(exchange.session_id);
      if (exchange.assistant_message?.content_text) {
        setMessages((m) => [
          ...m,
          {
            role: 'assistant',
            text: exchange.assistant_message!.content_text!,
          },
        ]);
      } else {
        setMessages((m) => [
          ...m,
          {
            role: 'assistant',
            text: t(
              exchange.error === 'inference_unavailable'
                ? 'chat.error_inference_down'
                : 'chat.error_generic',
            ),
            error: true,
          },
        ]);
      }
    } catch (err) {
      setMessages((m) => [
        ...m,
        { role: 'assistant', text: t('chat.error_generic'), error: true },
      ]);
    } finally {
      setSending(false);
    }
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
                  : m.error
                    ? 'mr-auto flex max-w-xs items-start gap-2 rounded bg-amber-50 px-3 py-2 text-sm text-amber-900'
                    : 'mr-auto flex max-w-xs items-start gap-2 rounded bg-leaf-100 px-3 py-2 text-sm text-soil-900'
              }
            >
              <span className="flex-1 whitespace-pre-line">{m.text}</span>
              {m.role === 'assistant' && !m.error && (
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
          {sending && (
            <li
              aria-live="polite"
              className="mr-auto rounded bg-leaf-100 px-3 py-2 text-sm italic text-soil-500"
            >
              {t('chat.thinking')}
            </li>
          )}
        </ul>
      </div>
      <div className="flex items-center gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          placeholder={t('chat.input_ph')}
          disabled={sending}
          className="flex-1 rounded border px-3 py-2 disabled:bg-soil-50"
        />
        <MicButton language={language} onTranscript={(text) => send(text)} />
        <button
          type="button"
          onClick={() => send()}
          disabled={sending || !input.trim()}
          className="btn-primary disabled:opacity-50"
        >
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
