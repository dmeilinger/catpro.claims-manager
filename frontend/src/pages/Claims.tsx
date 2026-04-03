import { useState, useCallback } from "react";
import { ClaimsTable } from "@/components/claims/ClaimsTable";
import { ClaimModal } from "@/components/claims/ClaimModal";
import { useClaims } from "@/hooks/useClaims";

export function Claims() {
  const [filters, setFilters] = useState({
    status: null as string | null,
    search: "",
  });
  const [page, setPage] = useState(1);
  const [selectedClaimId, setSelectedClaimId] = useState<number | null>(null);

  const { data, isLoading } = useClaims({
    page,
    page_size: 25,
    status: filters.status,
    search: filters.search || undefined,
  });

  const handleFilterChange = useCallback(
    (updates: { status?: string | null; search?: string }) => {
      setFilters((prev) => ({ ...prev, ...updates }));
      setPage(1);
    },
    []
  );

  return (
    <div className="space-y-4">
      <ClaimsTable
        items={data?.items ?? []}
        total={data?.total ?? 0}
        page={page}
        pageSize={25}
        isLoading={isLoading}
        filters={filters}
        onFilterChange={handleFilterChange}
        onPageChange={setPage}
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
