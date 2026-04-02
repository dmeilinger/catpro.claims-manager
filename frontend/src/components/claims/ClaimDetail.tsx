import { X, AlertCircle } from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import { useClaimDetail } from "@/hooks/useClaims";

interface ClaimDetailProps {
  claimId: number | null;
  onClose: () => void;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-2 border-b border-border pb-1">
        {title}
      </h4>
      <div className="space-y-1 text-sm">{children}</div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-foreground text-right max-w-[60%]">{value}</span>
    </div>
  );
}

function StatusBadge({ status, dryRun }: { status: string; dryRun: boolean }) {
  if (dryRun) {
    return <span className="text-info font-medium">Dry Run</span>;
  }
  const colors: Record<string, string> = {
    success: "text-success",
    error: "text-destructive",
    pending: "text-warning",
  };
  return (
    <span className={cn("font-medium capitalize", colors[status] || "text-muted-foreground")}>
      {status}
    </span>
  );
}

export function ClaimDetail({ claimId, onClose }: ClaimDetailProps) {
  const { data: claim, isLoading } = useClaimDetail(claimId);

  if (!claimId) return null;

  return (
    <div className="fixed right-0 top-0 h-full w-[400px] bg-card border-l border-border z-40 overflow-y-auto shadow-xl">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-border sticky top-0 bg-card">
        <h3 className="text-sm font-semibold text-foreground">Claim Detail</h3>
        <button
          onClick={onClose}
          className="p-1.5 rounded-md hover:bg-accent text-muted-foreground"
        >
          <X size={16} />
        </button>
      </div>

      {isLoading ? (
        <div className="p-4 space-y-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-4 bg-muted rounded animate-pulse" />
          ))}
        </div>
      ) : !claim ? (
        <div className="p-4 text-center text-muted-foreground">
          Claim not found
        </div>
      ) : (
        <div className="p-4 space-y-5">
          {/* Status header */}
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-muted-foreground text-sm">Status</span>
              <StatusBadge status={claim.status} dryRun={claim.dry_run} />
            </div>
            <Field label="Claim ID" value={claim.claim_id} />
            <Field label="Processed" value={formatDate(claim.processed_at)} />
            <Field label="Received" value={formatDate(claim.received_at)} />
          </div>

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
            </Section>
          )}

          {/* Loss Info */}
          {claim.claim_data && (
            <Section title="Loss Info">
              <Field label="Date" value={claim.claim_data.loss_date} />
              <Field label="Type" value={claim.claim_data.loss_type} />
              {claim.claim_data.loss_description && (
                <div>
                  <span className="text-muted-foreground text-sm">Description</span>
                  <p className="text-sm text-foreground mt-1">
                    {claim.claim_data.loss_description}
                  </p>
                </div>
              )}
              <Field label="Address" value={claim.claim_data.loss_address1} />
              <Field
                label="City/State"
                value={
                  [claim.claim_data.loss_city, claim.claim_data.loss_state, claim.claim_data.loss_zip]
                    .filter(Boolean)
                    .join(", ") || null
                }
              />
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

          {/* Submission Payload */}
          {claim.submission_payload && (
            <details className="group">
              <summary className="text-xs font-medium uppercase tracking-wider text-muted-foreground cursor-pointer hover:text-foreground">
                Submission Payload
              </summary>
              <pre className="mt-2 bg-background rounded-md p-3 text-xs text-muted-foreground overflow-x-auto max-h-[400px] overflow-y-auto">
                {JSON.stringify(claim.submission_payload, null, 2)}
              </pre>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
