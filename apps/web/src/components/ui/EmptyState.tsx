import { ReactNode } from 'react';

/**
 * Empty-state block — used when a list has no items, a search returns
 * nothing, an error blocks the page, etc.
 *
 * Centered vertically + horizontally inside whatever parent gives it
 * room. Pass an icon (lucide), title, description, and an optional CTA.
 */
export interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  /** Render compact (smaller spacing) — useful inside small cards. */
  compact?: boolean;
}

export default function EmptyState({
  icon,
  title,
  description,
  action,
  compact,
}: EmptyStateProps) {
  return (
    <div
      className={
        compact
          ? 'flex flex-col items-center justify-center gap-2 px-4 py-8 text-center'
          : 'flex flex-col items-center justify-center gap-3 px-6 py-16 text-center'
      }
    >
      {icon ? (
        <div
          className={
            compact
              ? 'mb-1 flex h-10 w-10 items-center justify-center rounded-full bg-leaf-100 text-leaf-700'
              : 'mb-2 flex h-14 w-14 items-center justify-center rounded-full bg-leaf-100 text-leaf-700'
          }
        >
          {icon}
        </div>
      ) : null}
      <h3
        className={
          compact
            ? 'font-display text-sm font-semibold text-ink-800'
            : 'font-display text-lg font-semibold text-ink-800'
        }
      >
        {title}
      </h3>
      {description ? (
        <p className="max-w-sm text-sm text-ink-500">{description}</p>
      ) : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
