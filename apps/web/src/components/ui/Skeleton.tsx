import { CSSProperties } from 'react';

/**
 * Shimmer skeleton primitive. Use these to mock the shape of incoming
 * content while it loads — feels faster than spinners.
 *
 * Pattern: render the same DOM layout as the loaded view, but replace
 * text / images with skeletons of approximately the same size. Don't
 * over-skeleton; 2-3 skeletons per visible card is plenty.
 */
export interface SkeletonProps {
  /** Tailwind class for width (e.g. ``w-24``, ``w-full``). */
  width?: string;
  /** Tailwind class for height (e.g. ``h-4``). Default ``h-4`` for text. */
  height?: string;
  /** Make it a circle (e.g. avatar placeholder). */
  circle?: boolean;
  /** Extra classes (margin, etc.). */
  className?: string;
  style?: CSSProperties;
}

export function Skeleton({
  width = 'w-full',
  height = 'h-4',
  circle,
  className,
  style,
}: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      style={style}
      className={`skeleton ${width} ${height} ${circle ? 'rounded-full' : ''} ${className ?? ''}`}
    />
  );
}

/** Common preset: a card-shaped block. */
export function SkeletonCard() {
  return (
    <div className="card flex flex-col gap-2">
      <Skeleton width="w-32" height="h-4" />
      <Skeleton width="w-full" height="h-3" />
      <Skeleton width="w-2/3" height="h-3" />
    </div>
  );
}

/** Common preset: a list-row with avatar + two lines. */
export function SkeletonRow() {
  return (
    <div className="flex items-center gap-3 px-1 py-2">
      <Skeleton width="w-12" height="h-12" circle />
      <div className="flex flex-1 flex-col gap-1.5">
        <Skeleton width="w-1/2" height="h-3.5" />
        <Skeleton width="w-1/3" height="h-3" />
      </div>
    </div>
  );
}
