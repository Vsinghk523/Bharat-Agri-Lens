import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Send, Sparkles, Volume2, VolumeX } from 'lucide-react';
import { api } from '@/lib/api';
import { useRequireAuth } from '@/lib/auth';
import AppBar from '@/components/ui/AppBar';
import MicButton from '@/components/MicButton';

interface Message {
  role: 'user' | 'assistant';
  text: string;
  error?: boolean;
}

/**
 * AI chat — full-height conversation surface.
 *
 * Layout: AppBar · scrolling message list · composer pinned to bottom.
 * The composer sits flush with the bottom-nav (we deliberately let it
 * scroll under the nav rather than padding around it, so the input
 * stays visible while typing without fighting the keyboard).
 *
 * Empty state surfaces 3 suggested-question chips so first-time users
 * have something to tap. Sending a chip triggers ``send(text)`` —
 * same code path as typing + send.
 */
export default function Chat() {
  useRequireAuth();
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ? `${i18n.resolvedLanguage}-IN` : 'en-IN';
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [playingIdx, setPlayingIdx] = useState<number | null>(null);
  const listEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listEnd.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, sending]);

  async function send(text?: string) {
    const body = (text ?? input).trim();
    if (!body || sending) return;
    setInput('');
    setSending(true);
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
          { role: 'assistant', text: exchange.assistant_message!.content_text! },
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
    } catch {
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
      const release = () => {
        URL.revokeObjectURL(url);
        setPlayingIdx((cur) => (cur === idx ? null : cur));
      };
      audio.onended = release;
      audio.onerror = release;
      await audio.play();
    } catch {
      setPlayingIdx((cur) => (cur === idx ? null : cur));
    }
  }

  const suggested = [t('chat.suggested_q1'), t('chat.suggested_q2'), t('chat.suggested_q3')];

  return (
    <>
      <AppBar title={t('chat.title')} subtitle={t('chat.subtitle')} />

      <div className="mx-auto flex max-w-2xl flex-col px-4 pb-32 pt-4 animate-fade-in">
        {messages.length === 0 ? (
          <div className="mt-8 flex flex-col items-center text-center">
            <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-leaf-100 text-leaf-700">
              <Sparkles className="h-6 w-6" />
            </div>
            <h2 className="font-display text-lg font-semibold text-ink-800">
              {t('chat.start_title')}
            </h2>
            <p className="mt-1 max-w-sm text-sm text-ink-500">{t('chat.start_hint')}</p>

            <ul className="mt-6 w-full space-y-2">
              {suggested.map((q, i) => (
                <li key={i}>
                  <button
                    type="button"
                    onClick={() => send(q)}
                    className="card w-full text-left transition-colors hover:border-leaf-200 hover:bg-leaf-50"
                  >
                    <p className="text-sm text-ink-700">{q}</p>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <ul className="space-y-2.5">
            {messages.map((m, i) => (
              <li
                key={i}
                className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}
              >
                <div
                  className={
                    m.role === 'user'
                      ? 'max-w-[80%] rounded-2xl rounded-tr-md bg-leaf-600 px-4 py-2.5 text-sm leading-snug text-white shadow-card'
                      : m.error
                        ? 'max-w-[80%] rounded-2xl rounded-tl-md border border-danger/30 bg-danger-soft px-4 py-2.5 text-sm leading-snug text-danger'
                        : 'flex max-w-[80%] items-start gap-2 rounded-2xl rounded-tl-md border border-ink-100 bg-white px-4 py-2.5 text-sm leading-snug text-ink-800 shadow-card'
                  }
                >
                  <span className="flex-1 whitespace-pre-line">{m.text}</span>
                  {m.role === 'assistant' && !m.error ? (
                    <button
                      type="button"
                      aria-label={t('chat.tts_play')}
                      onClick={() => playTts(m.text, i)}
                      disabled={playingIdx === i}
                      className="-mr-1 ml-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-ink-500 transition-colors hover:bg-ink-100 hover:text-ink-700 disabled:opacity-50"
                    >
                      {playingIdx === i ? (
                        <VolumeX className="h-4 w-4" />
                      ) : (
                        <Volume2 className="h-4 w-4" />
                      )}
                    </button>
                  ) : null}
                </div>
              </li>
            ))}
            {sending ? (
              <li aria-live="polite" className="flex justify-start">
                <div className="rounded-2xl rounded-tl-md border border-ink-100 bg-white px-4 py-2.5 text-sm italic text-ink-500 shadow-card">
                  <span className="inline-flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-leaf-500" />
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-leaf-500 [animation-delay:120ms]" />
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-leaf-500 [animation-delay:240ms]" />
                    <span className="ml-2">{t('chat.thinking')}</span>
                  </span>
                </div>
              </li>
            ) : null}
            <div ref={listEnd} />
          </ul>
        )}
      </div>

      {/* Pinned composer (sits above bottom-nav). */}
      <div
        className="fixed inset-x-0 z-30 border-t border-ink-100 bg-white/95 px-3 py-2 backdrop-blur supports-[backdrop-filter]:bg-white/85"
        style={{ bottom: 'calc(var(--bottom-nav-h) + var(--safe-bottom))' }}
      >
        <div className="mx-auto flex max-w-2xl items-center gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
            placeholder={t('chat.input_ph')}
            disabled={sending}
            className="input flex-1"
          />
          <MicButton language={language} onTranscript={(text) => send(text)} />
          <button
            type="button"
            onClick={() => send()}
            disabled={sending || !input.trim()}
            aria-label={t('chat.send')}
            className="btn-primary btn-icon"
          >
            <Send className="h-5 w-5" />
          </button>
        </div>
      </div>
    </>
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
