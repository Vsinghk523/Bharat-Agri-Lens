import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useRequireAuth } from '@/lib/auth';

export default function Chat() {
  useRequireAuth();
  const { t } = useTranslation();
  const [messages, setMessages] = useState<{ role: 'user' | 'assistant'; text: string }[]>([]);
  const [input, setInput] = useState('');

  function send() {
    if (!input.trim()) return;
    setMessages((m) => [
      ...m,
      { role: 'user', text: input },
      { role: 'assistant', text: t('chat.stub_reply') },
    ]);
    setInput('');
  }

  return (
    <section className="flex h-[70vh] flex-col gap-3 py-4">
      <h2 className="text-xl font-semibold text-leaf-700">{t('chat.title')}</h2>
      <div className="card flex-1 overflow-y-auto">
        {messages.length === 0 && <p className="text-sm text-soil-500">{t('chat.start_hint')}</p>}
        <ul className="space-y-2">
          {messages.map((m, i) => (
            <li
              key={i}
              className={
                m.role === 'user'
                  ? 'ml-auto max-w-xs rounded bg-leaf-600 px-3 py-2 text-sm text-white'
                  : 'mr-auto max-w-xs rounded bg-leaf-100 px-3 py-2 text-sm text-soil-900'
              }
            >
              {m.text}
            </li>
          ))}
        </ul>
      </div>
      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          placeholder={t('chat.input_ph')}
          className="flex-1 rounded border px-3 py-2"
        />
        <button type="button" onClick={send} className="btn-primary">
          {t('chat.send')}
        </button>
      </div>
    </section>
  );
}
