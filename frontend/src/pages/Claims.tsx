import { useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { ClaimsTable } from "@/components/claims/ClaimsTable";
import { ClaimModal } from "@/components/claims/ClaimModal";
import { useClaims } from "@/hooks/useClaims";

export function Claims() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedClaimId, setSelectedClaimId] = useState<number | null>(null);

  const status = searchParams.get("status");
  const search = searchParams.get("search") ?? "";
  const page = Number(searchParams.get("page") ?? 1);

  const { data, isLoading } = useClaims({
    page,
    page_size: 25,
    status,
    search: search || undefined,
  });

  const handleFilterChange = useCallback(
    (updates: { status?: string | null; search?: string }) => {
      setSearchParams(
        (prev) => {
          for (const [k, v] of Object.entries(updates)) {
            if (v == null || v === "") {
              prev.delete(k);
            } else {
              prev.set(k, v);
            }
          }
          prev.set("page", "1");
          return prev;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );

  const handlePageChange = useCallback(
    (newPage: number) => {
      setSearchParams(
        (prev) => {
          prev.set("page", String(newPage));
          return prev;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );

  return (
    <div className="space-y-4">
      <ClaimsTable
        items={data?.items ?? []}
        total={data?.total ?? 0}
        page={page}
        pageSize={25}
        isLoading={isLoading}
        filters={{ status, search }}
        onFilterChange={handleFilterChange}
        onPageChange={handlePageChange}
        onRowClick={setSelectedClaimId}
        selectedId={selectedClaimId}
      />

      <ClaimModal
        claimId={selectedClaimId}
        onClose={() => setSelectedClaimId(null)}
      />
    </div>
  );
}
