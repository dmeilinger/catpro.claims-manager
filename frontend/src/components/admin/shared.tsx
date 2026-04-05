import { cn } from "@/lib/utils";

export function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full transition-colors duration-200",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-900",
        "disabled:cursor-not-allowed disabled:opacity-40",
        checked ? "bg-blue-600" : "bg-zinc-600"
      )}
    >
      <span
        className={cn(
          "pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-md transition-transform duration-200 mt-0.5",
          checked ? "translate-x-5" : "translate-x-0.5"
        )}
      />
    </button>
  );
}

export function SettingRow({
  label,
  description,
  children,
}: {
  label: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-4 border-b border-border last:border-0">
      <div className="space-y-0.5">
        <p className="text-sm font-medium text-foreground">{label}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

export function InfoRow({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-3 border-b border-border last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm text-foreground text-right max-w-xs break-words">
        {value ?? "—"}
      </span>
    </div>
  );
}

const POLLER_STATUS_STYLES: Record<string, { dot: string; label: string }> = {
  idle:     { dot: "bg-green-500", label: "Idle" },
  running:  { dot: "bg-amber-400", label: "Running" },
  error:    { dot: "bg-red-500",   label: "Error" },
  disabled: { dot: "bg-zinc-500",  label: "Disabled" },
};

export function PollerStatusBadge({ status }: { status: string | null }) {
  const style = status
    ? (POLLER_STATUS_STYLES[status] ?? { dot: "bg-zinc-500", label: status })
    : { dot: "bg-zinc-600", label: "Never run" };
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={cn("inline-block h-2 w-2 rounded-full", style.dot)} />
      <span className="text-sm text-foreground">{style.label}</span>
    </span>
  );
}
