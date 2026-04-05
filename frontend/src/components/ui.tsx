/**
 * App-wide UI primitives shared across pages and components.
 */

import { cn } from "@/lib/utils";

/**
 * Standard table header cell — consistent column heading style across all tables.
 * Usage: <th> replacement inside <thead><tr>.
 * <Th>Date</Th>
 */
export function Th({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <th
      className={cn(
        "text-left px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-brand-fg",
        className
      )}
    >
      {children}
    </th>
  );
}

/**
 * Heading above a card/section group — title + optional description.
 * Usage: <SectionHeading title="Poller" description="Polls the M365 mailbox…" />
 */
export function SectionHeading({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div className="mb-3">
      <h2 className="text-base font-semibold text-foreground">{title}</h2>
      {description && (
        <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
      )}
    </div>
  );
}

/**
 * Labelled header bar for use inside a card, with the theme accent colour.
 * Wrap with a `rounded-lg border border-border overflow-hidden` container.
 * Usage: <CardHeader title="Overview" />
 */
export function CardHeader({ title }: { title: string }) {
  return (
    <div className="px-3 py-2 bg-brand/15 border-b border-brand/30">
      <h4 className="text-[11px] font-semibold uppercase tracking-wider text-brand-fg">
        {title}
      </h4>
    </div>
  );
}

/**
 * Full card section — bordered card with accent header bar + slotted content.
 * Rows inside should use `divide-y divide-border/60`.
 * Usage:
 *   <CardSection title="Insured">
 *     <div className="divide-y divide-border/60">…</div>
 *   </CardSection>
 */
export function CardSection({
  title,
  children,
  className,
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("rounded-lg border border-border overflow-hidden", className)}>
      <CardHeader title={title} />
      <div className="text-sm">{children}</div>
    </div>
  );
}
