import { useState } from "react";
import { ChevronRight, ChevronDown, Flag } from "lucide-react";
import { cn } from "@/lib/utils";
import { useEmailLog, type EmailLogParams } from "@/hooks/useEmailLog";
import { useTriageAction } from "@/hooks/useInbox";
import type { EmailLogEntry, EmailLogStats } from "@/schemas/email";

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

const STATUS_COLORS: Record<string, string> = {
  success: "text-green-600 dark:text-green-400",
  error: "text-red-600 dark:text-red-400",
  skipped: "text-muted-foreground",
  pending: "text-yellow-600 dark:text-yellow-400",
};

const TRIAGE_LABELS: Record<string, string> = {
  unreviewed: "Unreviewed",
  needs_review: "Needs Review",
  actioned: "Actioned",
};

function StatsChips({
  stats,
  activeFilter,
  onFilter,
}: {
  stats: EmailLogStats;
  activeFilter: string | null;
  onFilter: (status: string | null) => void;
}) {
  const chips: { key: string; label: string; count: number }[] = [
    { key: "all", label: "Total", count: stats.total },
    { key: "success", label: "Claims", count: stats.success },
    { key: "skipped", label: "Skipped", count: stats.skipped },
    { key: "error", label: "Errors", count: stats.error },
    { key: "dry_run", label: "Dry Run", count: stats.dry_run },
  ];

  return (
    <div className="flex flex-wrap gap-2">
      {chips.map(({ key, label, count }) => {
        const isActive = key === "all" ? activeFilter === null : activeFilter === key;
        return (
          <button
            key={key}
            onClick={() => onFilter(isActive ? null : key === "all" ? null : key)}
            className={cn(
              "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors",
              isActive
                ? "bg-amber-500 text-white"
                : "bg-muted text-muted-foreground hover:bg-accent hover:text-foreground"
            )}
          >
            {label}
            <span className={cn(
              "font-semibold tabular-nums",
              isActive ? "text-white/90" : ""
            )}>{count}</span>
            {isActive && <span className="ml-0.5 opacity-75">✕</span>}
          </button>
        );
      })}
    </div>
  );
}

function EmailHistoryRow({ item }: { item: EmailLogEntry }) {
  const [expanded, setExpanded] = useState(false);
  const { mutate: triage, isPending } = useTriageAction();
  const canFlag = item.triage_status !== "needs_review";

  return (
    <>
      <tr
        className="hover:bg-accent/50 cursor-pointer transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <td className="w-6 px-3 py-2.5 text-muted-foreground">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </td>
        <td className="px-3 py-2.5 text-xs text-muted-foreground whitespace-nowrap">
          {formatDate(item.received_at)}
        </td>
        <td className="px-3 py-2.5 text-xs max-w-[160px] truncate">{item.sender ?? "—"}</td>
        <td className="px-3 py-2.5 text-xs max-w-[260px] truncate font-medium">{item.subject ?? "(no subject)"}</td>
        <td className="px-3 py-2.5 text-xs">
          <span className={cn("font-medium", STATUS_COLORS[item.status] ?? "")}>
            {item.status}
          </span>
        </td>
        <td className="px-3 py-2.5 text-xs text-muted-foreground">
          {TRIAGE_LABELS[item.triage_status] ?? item.triage_status}
        </td>
        <td className="px-3 py-2.5 text-xs text-muted-foreground">
          {item.claim_id ?? item.insured_name ?? "—"}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-accent/20">
          <td colSpan={7} className="px-6 py-3">
            <div className="space-y-2 text-xs">
              {item.error_message && (
                <p className="text-red-600 dark:text-red-400">
                  <span className="font-medium">Error:</span> {item.error_message}
                </p>
              )}
              <p className="text-muted-foreground">
                Received: {formatDate(item.received_at)} · Processed: {formatDate(item.processed_at)}
                · Triage: {TRIAGE_LABELS[item.triage_status] ?? item.triage_status}
                {item.dry_run && " · Dry Run"}
              </p>
              {item.body_text && (
                <details className="pt-1">
                  <summary className="cursor-pointer text-muted-foreground hover:text-foreground select-none">
                    Email body
                  </summary>
                  <pre className="mt-2 whitespace-pre-wrap font-sans text-xs text-foreground bg-muted/50 rounded p-3 max-h-64 overflow-y-auto border border-border">
                    {item.body_text}
                  </pre>
                </details>
              )}
              {canFlag && (
                <button
                  disabled={isPending}
                  onClick={(e) => { e.stopPropagation(); triage({ id: item.id, action: "flag_review" }); }}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded border border-amber-300 text-amber-700 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-900/20 transition-colors disabled:opacity-50"
                >
                  <Flag size={11} />
                  Flag for Review
                </button>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export function EmailHistory() {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [triageFilter, setTriageFilter] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const PAGE_SIZE = 50;

  const params: EmailLogParams = {
    page,
    page_size: PAGE_SIZE,
    status: statusFilter,
    triage_status: triageFilter || null,
    search: search.length >= 2 ? search : null,
    from: fromDate || null,
    to: toDate || null,
  };

  const { data, isLoading } = useEmailLog(params);

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const stats = data?.stats;

  const handleStatusFilter = (s: string | null) => {
    setStatusFilter(s === "dry_run" ? null : s);
    setPage(1);
  };

  return (
    <div className="space-y-4">
      {stats && (
        <StatsChips
          stats={stats}
          activeFilter={statusFilter}
          onFilter={handleStatusFilter}
        />
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-end">
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">Triage</label>
          <select
            value={triageFilter ?? ""}
            onChange={(e) => { setTriageFilter(e.target.value || null); setPage(1); }}
            className="text-xs px-2 py-1.5 rounded-md border border-border bg-background"
          >
            <option value="">All</option>
            <option value="unreviewed">Unreviewed</option>
            <option value="needs_review">Needs Review</option>
            <option value="actioned">Actioned</option>
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">From</label>
          <input
            type="date"
            value={fromDate}
            onChange={(e) => { setFromDate(e.target.value); setPage(1); }}
            className="text-xs px-2 py-1.5 rounded-md border border-border bg-background"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">To</label>
          <input
            type="date"
            value={toDate}
            onChange={(e) => { setToDate(e.target.value); setPage(1); }}
            className="text-xs px-2 py-1.5 rounded-md border border-border bg-background"
          />
        </div>
        <div className="space-y-1 flex-1 min-w-[160px]">
          <label className="text-xs text-muted-foreground">Search</label>
          <input
            type="text"
            placeholder="sender or subject…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            className="w-full text-xs px-2 py-1.5 rounded-md border border-border bg-background"
          />
        </div>
      </div>

      {isLoading ? (
        <div className="text-muted-foreground text-sm">Loading…</div>
      ) : (
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 border-b border-border">
              <tr>
                <th className="w-6 px-3 py-2" />
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Received</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Sender</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Subject</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Status</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Triage</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Claim / Insured</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {items.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-3 py-8 text-center text-sm text-muted-foreground">
                    No emails match the current filters.
                  </td>
                </tr>
              ) : (
                items.map((item) => <EmailHistoryRow key={item.id} item={item} />)
              )}
            </tbody>
          </table>
        </div>
      )}

      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            {total} total · Page {page} of {Math.ceil(total / PAGE_SIZE)}
          </span>
          <div className="flex gap-2">
            <button
              disabled={page === 1}
              onClick={() => setPage(page - 1)}
              className="px-3 py-1.5 rounded-md border border-border disabled:opacity-50 hover:bg-accent text-xs"
            >
              Previous
            </button>
            <button
              disabled={page * PAGE_SIZE >= total}
              onClick={() => setPage(page + 1)}
              className="px-3 py-1.5 rounded-md border border-border disabled:opacity-50 hover:bg-accent text-xs"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
