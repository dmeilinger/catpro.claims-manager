import { useEffect } from "react";
import { X, AlertCircle } from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import { useClaimDetail } from "@/hooks/useClaims";

interface ClaimModalProps {
  claimId: number | null;
  onClose: () => void;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <div className="px-3 py-2 bg-primary/8 border-b border-primary/20">
        <h4 className="text-[11px] font-semibold uppercase tracking-wider text-primary/70">
          {title}
        </h4>
      </div>
      <div className="divide-y divide-border/60 text-sm">{children}</div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <div className="flex justify-between gap-4 px-3 py-2.5">
      <span className="text-muted-foreground shrink-0">{label}</span>
      <span className="text-foreground text-right">{value}</span>
    </div>
  );
}

function StatusBadge({ status, dryRun }: { status: string; dryRun: boolean }) {
  if (dryRun) {
    return (
      <span className="inline-flex items-center px-2.5 py-0.5 rounded text-xs font-medium bg-info/15 text-info border border-info/25">
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
        "inline-flex items-center px-2.5 py-0.5 rounded text-xs font-medium border",
        styles[status] || "bg-muted text-muted-foreground border-border"
      )}
    >
      {status === "success" ? "Success" : status === "error" ? "Error" : "Pending"}
    </span>
  );
}

export function ClaimModal({ claimId, onClose }: ClaimModalProps) {
  const { data: claim, isLoading } = useClaimDetail(claimId);

  // Close on Escape key
  useEffect(() => {
    if (!claimId) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [claimId, onClose]);

  if (!claimId) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-card border border-border rounded-lg shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col mx-4">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
          <div className="flex items-center gap-3">
            <h3 className="text-base font-semibold text-foreground">
              Claim Detail
            </h3>
            {claim && (
              <StatusBadge status={claim.status} dryRun={claim.dry_run} />
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1 px-6 py-5">
          {isLoading ? (
            <div className="space-y-4">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-4 bg-muted rounded animate-pulse" />
              ))}
            </div>
          ) : !claim ? (
            <div className="text-center text-muted-foreground py-8">
              Claim not found
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Left column */}
              <div className="space-y-4">
                {/* Overview */}
                <Section title="Overview">
                  <Field label="Claim ID" value={claim.claim_id} />
                  <Field label="Subject" value={claim.subject} />
                  <Field label="Sender" value={claim.sender} />
                  <Field label="Processed" value={formatDate(claim.processed_at)} />
                  <Field label="Received" value={formatDate(claim.received_at)} />
                </Section>

                {/* Error message */}
                {claim.error_message && (
                  <div className="bg-destructive/10 border border-destructive/25 rounded-md p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <AlertCircle size={14} className="text-destructive" />
                      <span className="text-xs font-medium text-destructive">
                        Error
                      </span>
                    </div>
                    <p className="text-sm text-foreground whitespace-pre-wrap">
                      {claim.error_message}
                    </p>
                  </div>
                )}

                {/* Insured */}
                {claim.claim_data && (
                  <Section title="Insured">
                    <Field
                      label="Name"
                      value={
                        [claim.claim_data.insured_first_name, claim.claim_data.insured_last_name]
                          .filter(Boolean)
                          .join(" ") || null
                      }
                    />
                    <Field label="Phone" value={claim.claim_data.insured_phone} />
                    <Field label="Cell" value={claim.claim_data.insured_cell} />
                    <Field label="Email" value={claim.claim_data.insured_email} />
                    <Field label="Address" value={claim.claim_data.insured_address1} />
                    <Field
                      label="City/State"
                      value={
                        [claim.claim_data.insured_city, claim.claim_data.insured_state, claim.claim_data.insured_zip]
                          .filter(Boolean)
                          .join(", ") || null
                      }
                    />
                    {(claim.claim_data.secondary_insured_first || claim.claim_data.secondary_insured_last) && (
                      <Field
                        label="Secondary"
                        value={
                          [claim.claim_data.secondary_insured_first, claim.claim_data.secondary_insured_last]
                            .filter(Boolean)
                            .join(" ") || null
                        }
                      />
                    )}
                  </Section>
                )}
              </div>

              {/* Right column */}
              <div className="space-y-4">
                {/* Loss Info */}
                {claim.claim_data && (
                  <Section title="Loss Info">
                    <Field label="Date" value={claim.claim_data.loss_date} />
                    <Field label="Type" value={claim.claim_data.loss_type} />
                    <Field label="Address" value={claim.claim_data.loss_address1} />
                    <Field
                      label="City/State"
                      value={
                        [claim.claim_data.loss_city, claim.claim_data.loss_state, claim.claim_data.loss_zip]
                          .filter(Boolean)
                          .join(", ") || null
                      }
                    />
                    {claim.claim_data.loss_description && (
                      <div className="px-3 py-2.5">
                        <span className="text-muted-foreground text-sm">Description</span>
                        <p className="text-sm text-foreground mt-1 leading-relaxed">
                          {claim.claim_data.loss_description}
                        </p>
                      </div>
                    )}
                  </Section>
                )}

                {/* Policy */}
                {claim.claim_data && (
                  <Section title="Policy">
                    <Field label="Number" value={claim.claim_data.policy_number} />
                    <Field label="Effective" value={claim.claim_data.policy_effective} />
                    <Field label="Expiration" value={claim.claim_data.policy_expiration} />
                    <Field label="Company" value={claim.claim_data.client_company_name} />
                    <Field label="Claim #" value={claim.claim_data.client_claim_number} />
                  </Section>
                )}

                {/* FileTrac IDs */}
                {claim.resolved_ids && (
                  <Section title="FileTrac IDs">
                    {Object.entries(claim.resolved_ids).map(([key, val]) =>
                      val ? <Field key={key} label={key} value={val} /> : null
                    )}
                  </Section>
                )}
              </div>

              {/* Full width: Submission Payload */}
              {claim.submission_payload && (
                <div className="col-span-full rounded-lg border border-border overflow-hidden">
                  <details className="group">
                    <summary className="flex items-center gap-2 px-3 py-2 bg-primary/8 border-b border-primary/20 cursor-pointer hover:bg-primary/12 transition-colors list-none">
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-primary/70">
                        ▶ Submission Payload
                      </span>
                    </summary>
                    <pre className="bg-background p-3 text-xs text-muted-foreground overflow-x-auto max-h-[300px] overflow-y-auto">
                      {JSON.stringify(claim.submission_payload, null, 2)}
                    </pre>
                  </details>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
