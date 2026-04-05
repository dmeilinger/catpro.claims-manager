import { useState, useEffect } from "react";
import { Search, ChevronLeft, ChevronRight } from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import { Th } from "@/components/ui";
import type { ClaimSummary } from "@/schemas/claim";

interface ClaimsTableProps {
  items: ClaimSummary[];
  total: number;
  page: number;
  pageSize: number;
  isLoading: boolean;
  filters: {
    status: string | null;
    search: string;
  };
  onFilterChange: (filters: { status?: string | null; search?: string }) => void;
  onPageChange: (page: number) => void;
  onRowClick: (id: number) => void;
  selectedId: number | null;
}

function StatusBadge({ status, dryRun }: { status: string; dryRun: boolean }) {
  if (dryRun) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-info/15 text-info border border-info/25">
        Dry Run
      </span>
    );
  }
  const styles: Record<string, string> = {
    success: "bg-success/15 text-success border-success/25",
    error: "bg-destructive/15 text-destructive border-destructive/25",
    pending: "bg-warning/15 text-warning border-warning/25",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border",
        styles[status] || "bg-muted text-muted-foreground border-border"
      )}
    >
      {status === "success" ? "Success" : status === "error" ? "Error" : "Pending"}
    </span>
  );
}

export function ClaimsTable({
  items,
  total,
  page,
  pageSize,
  isLoading,
  filters,
  onFilterChange,
  onPageChange,
  onRowClick,
  selectedId,
}: ClaimsTableProps) {
  const [localSearch, setLocalSearch] = useState(filters.search);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => {
      onFilterChange({ search: localSearch || undefined });
    }, 300);
    return () => clearTimeout(timer);
  }, [localSearch]);

  return (
    <div className="space-y-3">
      {/* Filter bar */}
      <div className="flex items-center gap-3 bg-card rounded-lg border border-border p-3">
        <select
          value={filters.status || ""}
          onChange={(e) =>
            onFilterChange({ status: e.target.value || null })
          }
          className="bg-input border border-border rounded-md px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        >
          <option value="">All Status</option>
          <option value="success">Success</option>
          <option value="error">Error</option>
          <option value="pending">Pending</option>
        </select>

        <div className="relative flex-1">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <input
            type="text"
            value={localSearch}
            onChange={(e) => setLocalSearch(e.target.value)}
            placeholder="Search claims..."
            className="w-full bg-input border border-border rounded-md pl-9 pr-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
      </div>

      {/* Table */}
      <div className="bg-card rounded-lg border border-border overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-brand/15 border-b border-brand/30">
              <Th>Date</Th>
              <Th>Subject</Th>
              <Th>Insured</Th>
              <Th>Status</Th>
              <Th>Claim ID</Th>
            </tr>
          </thead>
          <tbody>
            {isLoading &&
              items.length === 0 &&
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i} className="border-b border-border">
                  {Array.from({ length: 5 }).map((_, j) => (
                    <td key={j} className="px-4 py-3">
                      <div className="h-4 w-24 bg-muted rounded animate-pulse" />
                    </td>
                  ))}
                </tr>
              ))}

            {!isLoading && items.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="px-4 py-12 text-center text-muted-foreground"
                >
                  {filters.search || filters.status
                    ? "No claims match your filters."
                    : "No claims processed yet. Start the poller to begin."}
                </td>
              </tr>
            )}

            {items.map((claim) => (
              <tr
                key={claim.id}
                onClick={() => onRowClick(claim.id)}
                className={cn(
                  "border-b border-border cursor-pointer transition-colors",
                  selectedId === claim.id
                    ? "bg-primary/5"
                    : "hover:bg-accent"
                )}
              >
                <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                  {formatDate(claim.processed_at)}
                </td>
                <td className="px-4 py-3 text-foreground">{claim.subject || "--"}</td>
                <td className="px-4 py-3 text-foreground">
                  {claim.insured_name || "--"}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={claim.status} dryRun={claim.dry_run} />
                </td>
                <td className="px-4 py-3 text-muted-foreground font-mono text-xs">
                  {claim.dry_run
                    ? "DRY"
                    : claim.claim_id
                      ? claim.claim_id.replace("claimID=", "")
                      : "--"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Pagination */}
        {total > 0 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-border">
            <span className="text-xs text-muted-foreground">
              Showing {(page - 1) * pageSize + 1}-
              {Math.min(page * pageSize, total)} of {total}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => onPageChange(page - 1)}
                disabled={page <= 1}
                className="p-1.5 rounded-md hover:bg-accent disabled:opacity-30 disabled:cursor-not-allowed text-muted-foreground"
              >
                <ChevronLeft size={16} />
              </button>
              {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                const p = i + 1;
                return (
                  <button
                    key={p}
                    onClick={() => onPageChange(p)}
                    className={cn(
                      "w-8 h-8 rounded-md text-xs",
                      p === page
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:bg-accent"
                    )}
                  >
                    {p}
                  </button>
                );
              })}
              <button
                onClick={() => onPageChange(page + 1)}
                disabled={page >= totalPages}
                className="p-1.5 rounded-md hover:bg-accent disabled:opacity-30 disabled:cursor-not-allowed text-muted-foreground"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
