import { ButtonHTMLAttributes, forwardRef, ReactNode } from 'react';

/**
 * Square icon button — wraps a lucide icon and a hidden accessible
 * label. Use for app-bar trailing icons, list-row actions, etc.
 *
 * The badge prop adds a small number bubble (notification count,
 * unread messages, etc.). Pass null to hide.
 */
export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Visually-hidden label. Required for screen readers. */
  label: string;
  /** Number badge (1–99+) or null to hide. */
  badge?: number | null;
  /** Visual variant — defaults to ghost. */
  variant?: 'ghost' | 'secondary';
  /** Smaller (32px) instead of default (40px). */
  size?: 'sm' | 'md';
  /** lucide icon (or any small ReactNode). */
  children: ReactNode;
}

export default forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, badge, variant = 'ghost', size = 'md', className, children, ...rest },
  ref,
) {
  const baseClass =
    variant === 'secondary'
      ? size === 'sm'
        ? 'btn-secondary btn-icon btn-sm'
        : 'btn-secondary btn-icon'
      : size === 'sm'
        ? 'btn-ghost btn-icon btn-sm'
        : 'btn-ghost btn-icon';

  return (
    <button
      ref={ref}
      type="button"
      aria-label={label}
      className={`relative ${baseClass} ${className ?? ''}`}
      {...rest}
    >
      {children}
      {badge != null && badge > 0 ? (
        <span
          aria-hidden="true"
          className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-danger px-1 text-[10px] font-semibold leading-none text-white"
        >
          {badge > 99 ? '99+' : badge}
        </span>
      ) : null}
    </button>
  );
});
