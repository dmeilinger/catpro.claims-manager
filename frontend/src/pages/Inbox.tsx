import { useState } from "react";
import { Inbox as InboxIcon, ChevronRight, ChevronDown, AlertCircle, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useInbox, useTriageAction } from "@/hooks/useInbox";
import type { InboxEntry } from "@/schemas/email";

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function StatusBadge({ status }: { status: string }) {
  const isError = status === "error";
  return (
    <span className={cn(
      "inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full",
      isError
        ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
        : "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400"
    )}>
      {isError ? <AlertCircle size={10} /> : <CheckCircle2 size={10} />}
      {status}
    </span>
  );
}

function InboxRow({ item }: { item: InboxEntry }) {
  const [expanded, setExpanded] = useState(false);
  const { mutate: triage, isPending } = useTriageAction();

  return (
    <>
      <tr
        className="hover:bg-accent/50 cursor-pointer transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <td className="w-6 px-3 py-3 text-muted-foreground">
          {expanded
            ? <ChevronDown size={14} />
            : <ChevronRight size={14} />}
        </td>
        <td className="px-3 py-3 text-sm text-muted-foreground whitespace-nowrap">
          {formatDate(item.received_at)}
        </td>
        <td className="px-3 py-3 text-sm max-w-[200px] truncate">
          {item.sender ?? "—"}
        </td>
        <td className="px-3 py-3 text-sm max-w-[300px] truncate font-medium">
          {item.subject ?? "(no subject)"}
        </td>
        <td className="px-3 py-3">
          <StatusBadge status={item.status} />
        </td>
      </tr>
      {expanded && (
        <tr className="bg-accent/20">
          <td colSpan={5} className="px-6 py-4">
            <div className="space-y-3">
              {item.insured_name && (
                <p className="text-sm"><span className="text-muted-foreground">Insured:</span> {item.insured_name}</p>
              )}
              {item.error_message && (
                <p className="text-sm text-red-600 dark:text-red-400">
                  <span className="font-medium">Error:</span> {item.error_message}
                </p>
              )}
              <p className="text-xs text-muted-foreground">
                Received: {formatDate(item.received_at)} · Processed: {formatDate(item.processed_at)}
              </p>
              <div className="flex gap-2 pt-1">
                <button
                  disabled={isPending}
                  onClick={(e) => { e.stopPropagation(); triage({ id: item.id, action: "dismiss" }); }}
                  className="px-3 py-1.5 text-xs rounded-md border border-border hover:bg-accent transition-colors disabled:opacity-50"
                >
                  Dismiss
                </button>
                <button
                  disabled={isPending}
                  onClick={(e) => { e.stopPropagation(); triage({ id: item.id, action: "approve" }); }}
                  className="px-3 py-1.5 text-xs rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
                >
                  Approve
                </button>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export function InboxPage() {
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 25;
  const { data, isLoading } = useInbox({ page, page_size: PAGE_SIZE });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  if (isLoading) {
    return <div className="text-muted-foreground text-sm">Loading inbox…</div>;
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <InboxIcon size={40} className="text-muted-foreground mb-4 opacity-40" />
        <h3 className="text-sm font-medium text-foreground">All clear</h3>
        <p className="text-sm text-muted-foreground mt-1">No emails need review right now.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        {total} {total === 1 ? "case needs" : "cases need"} review
      </p>

      <div className="rounded-lg border border-border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 border-b border-border">
            <tr>
              <th className="w-6 px-3 py-2" />
              <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Received</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Sender</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Subject</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {items.map((item) => (
              <InboxRow key={item.id} item={item} />
            ))}
          </tbody>
        </table>
      </div>

      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            Page {page} of {Math.ceil(total / PAGE_SIZE)}
          </span>
          <div className="flex gap-2">
            <button
              disabled={page === 1}
              onClick={() => setPage(page - 1)}
              className="px-3 py-1.5 rounded-md border border-border disabled:opacity-50 hover:bg-accent"
            >
              Previous
            </button>
            <button
              disabled={page * PAGE_SIZE >= total}
              onClick={() => setPage(page + 1)}
              className="px-3 py-1.5 rounded-md border border-border disabled:opacity-50 hover:bg-accent"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
