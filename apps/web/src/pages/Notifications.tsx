import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bell, CheckCircle2, CloudRain, FileText, Sparkles } from 'lucide-react';
import { useRequireAuth } from '@/lib/auth';
import AppBar from '@/components/ui/AppBar';
import EmptyState from '@/components/ui/EmptyState';

/**
 * Notifications inbox.
 *
 * For v0 we render a small set of placeholder notifications so the
 * UI surface is reviewable. When push / FCM lands in v0.1 the list
 * gets fed from a real ``api.notifications.list()`` call (kept the
 * shape consistent so the swap is cheap).
 *
 * Each row: icon · title · body · timestamp. Tapping marks it read
 * (locally for now; persisted in v0.1).
 */
interface Notification {
  id: string;
  kind: 'diagnosis' | 'weather' | 'article';
  title: string;
  body: string;
  when: 'today' | 'earlier';
  read: boolean;
}

const SAMPLE: Notification[] = [
  {
    id: '1',
    kind: 'diagnosis',
    title: 'Diagnosis reviewed',
    body: 'Your Tomato scan was reviewed by Dr. Sharma (KVK Lucknow).',
    when: 'today',
    read: false,
  },
  {
    id: '2',
    kind: 'weather',
    title: 'Weather alert',
    body: 'Heavy rain expected tomorrow. Postpone any planned spray.',
    when: 'today',
    read: false,
  },
  {
    id: '3',
    kind: 'article',
    title: 'New article',
    body: 'Best practices for managing Tomato Late Blight in monsoon season.',
    when: 'earlier',
    read: true,
  },
];

const ICON: Record<Notification['kind'], React.ReactNode> = {
  diagnosis: <CheckCircle2 className="h-4 w-4" />,
  weather: <CloudRain className="h-4 w-4" />,
  article: <FileText className="h-4 w-4" />,
};

const ACCENT: Record<Notification['kind'], string> = {
  diagnosis: 'bg-success-soft text-success',
  weather: 'bg-saffron-100 text-saffron-700',
  article: 'bg-leaf-100 text-leaf-700',
};

export default function Notifications() {
  useRequireAuth();
  const { t } = useTranslation();
  const [list, setList] = useState(SAMPLE);

  const unread = list.filter((n) => !n.read).length;
  const today = list.filter((n) => n.when === 'today');
  const earlier = list.filter((n) => n.when === 'earlier');

  function markAllRead() {
    setList((prev) => prev.map((n) => ({ ...n, read: true })));
  }

  return (
    <>
      <AppBar
        showBack
        title={t('notifications.title')}
        trailing={
          unread > 0 ? (
            <button
              type="button"
              onClick={markAllRead}
              className="text-xs font-semibold text-leaf-700 hover:text-leaf-800"
            >
              {t('notifications.mark_all_read')}
            </button>
          ) : null
        }
      />

      <div className="mx-auto max-w-2xl px-4 py-4 animate-fade-in">
        {list.length === 0 ? (
          <EmptyState
            icon={<Sparkles className="h-6 w-6" />}
            title={t('notifications.empty_title')}
            description={t('notifications.empty_subtitle')}
          />
        ) : (
          <>
            {today.length > 0 ? (
              <Section
                heading={t('notifications.today')}
                items={today}
                onRead={(id) =>
                  setList((prev) =>
                    prev.map((n) => (n.id === id ? { ...n, read: true } : n)),
                  )
                }
              />
            ) : null}
            {earlier.length > 0 ? (
              <Section
                heading={t('notifications.earlier')}
                items={earlier}
                onRead={(id) =>
                  setList((prev) =>
                    prev.map((n) => (n.id === id ? { ...n, read: true } : n)),
                  )
                }
              />
            ) : null}
          </>
        )}
      </div>
    </>
  );
}

function Section({
  heading,
  items,
  onRead,
}: {
  heading: string;
  items: Notification[];
  onRead: (id: string) => void;
}) {
  return (
    <section className="mb-5">
      <h3 className="section-heading">{heading}</h3>
      <ul className="space-y-2">
        {items.map((n) => (
          <li key={n.id}>
            <button
              type="button"
              onClick={() => onRead(n.id)}
              className={`card flex w-full items-start gap-3 text-left transition-colors ${
                n.read ? '' : 'border-leaf-200 bg-leaf-50/40'
              }`}
            >
              <span
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${ACCENT[n.kind]}`}
              >
                {ICON[n.kind]}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="font-medium text-ink-800">{n.title}</p>
                  {!n.read ? (
                    <span
                      className="h-1.5 w-1.5 rounded-full bg-leaf-600"
                      aria-label="unread"
                    />
                  ) : null}
                </div>
                <p className="mt-0.5 text-sm leading-snug text-ink-600">{n.body}</p>
              </div>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
