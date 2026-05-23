import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Mic } from 'lucide-react';
import { api } from '@/lib/api';

type State = 'idle' | 'recording' | 'transcribing' | 'unsupported';

interface Props {
  language: string;
  onTranscript: (text: string) => void;
}

/**
 * Press-and-hold microphone button. Records via MediaRecorder while
 * held, base64-encodes the resulting blob on release, posts to
 * /voice/stt, and emits the transcript to the parent.
 *
 * Permissions are requested lazily on first tap so the user sees the
 * browser prompt in response to a click (Firefox / Safari will block
 * a prompt issued from an effect at mount time).
 */
export default function MicButton({ language, onTranscript }: Props) {
  const { t } = useTranslation();
  const [state, setState] = useState<State>('idle');
  const [error, setError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setState('unsupported');
    }
  }, []);

  // Always release the mic on unmount.
  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const startRecording = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      // MediaRecorder picks the best mimeType the platform supports.
      const recorder = new MediaRecorder(stream);
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = async () => {
        const blob = new Blob(chunksRef.current, {
          type: recorder.mimeType || 'audio/webm',
        });
        streamRef.current?.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        if (blob.size === 0) {
          setState('idle');
          return;
        }
        setState('transcribing');
        try {
          const buf = await blob.arrayBuffer();
          const audio_b64 = bytesToBase64(new Uint8Array(buf));
          const resp = await api.voice.stt({ audio_b64, language });
          if (resp.transcript) onTranscript(resp.transcript);
        } catch (err) {
          setError(err instanceof Error ? err.message : 'Transcription failed');
        } finally {
          setState('idle');
        }
      };
      recorderRef.current = recorder;
      recorder.start();
      setState('recording');
    } catch (err) {
      setState('idle');
      setError(err instanceof Error ? err.message : 'Microphone unavailable');
    }
  }, [language, onTranscript]);

  const stopRecording = useCallback(() => {
    const rec = recorderRef.current;
    if (rec && rec.state !== 'inactive') {
      rec.stop();
    }
  }, []);

  if (state === 'unsupported') {
    return null;
  }

  const label =
    state === 'recording'
      ? t('chat.mic_recording')
      : state === 'transcribing'
        ? t('chat.mic_processing')
        : t('chat.mic_start');

  return (
    <div className="relative">
      <button
        type="button"
        aria-label={label}
        aria-pressed={state === 'recording'}
        onMouseDown={state === 'idle' ? startRecording : undefined}
        onMouseUp={stopRecording}
        onMouseLeave={state === 'recording' ? stopRecording : undefined}
        onTouchStart={state === 'idle' ? startRecording : undefined}
        onTouchEnd={stopRecording}
        disabled={state === 'transcribing'}
        className={
          state === 'recording'
            ? 'relative flex h-11 w-11 items-center justify-center rounded-full bg-danger text-white shadow-card transition-all'
            : state === 'transcribing'
              ? 'flex h-11 w-11 cursor-wait items-center justify-center rounded-full bg-ink-100 text-ink-500'
              : 'flex h-11 w-11 items-center justify-center rounded-full border border-ink-200 bg-white text-ink-600 shadow-card transition-all hover:border-leaf-300 hover:bg-leaf-50 hover:text-leaf-700 active:scale-95'
        }
      >
        {state === 'recording' ? (
          <>
            <span className="pointer-events-none absolute inset-0 rounded-full bg-danger/40 animate-pulse-ring" />
            <Mic className="relative h-5 w-5" />
          </>
        ) : state === 'transcribing' ? (
          <Loader2 className="h-5 w-5 animate-spin" />
        ) : (
          <Mic className="h-5 w-5" />
        )}
      </button>
      {error ? (
        <p className="absolute left-1/2 top-full mt-1 w-32 -translate-x-1/2 text-center text-[10px] text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/**
 * Base64-encode an arbitrary Uint8Array. Browser's btoa() requires a
 * binary string, and going through TextDecoder would corrupt bytes
 * outside latin-1. This loop is safe for any byte sequence.
 */
function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}
