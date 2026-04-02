import { useState, useCallback } from "react";
import { SummaryCards } from "@/components/dashboard/SummaryCards";
import { TrendChart } from "@/components/dashboard/TrendChart";
import { ClaimsTable } from "@/components/claims/ClaimsTable";
import { ClaimDetail } from "@/components/claims/ClaimDetail";
import { useClaims, useClaimTrends } from "@/hooks/useClaims";

export function Dashboard() {
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

  const { data: trends, isLoading: trendsLoading } = useClaimTrends();

  const handleFilterChange = useCallback(
    (updates: { status?: string | null; search?: string }) => {
      setFilters((prev) => ({ ...prev, ...updates }));
      setPage(1); // Reset to page 1 on filter change
    },
    []
  );

  return (
    <div className="space-y-6">
      <SummaryCards stats={data?.stats} isLoading={isLoading} />

      <TrendChart data={trends?.data} isLoading={trendsLoading} />

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

      <ClaimDetail
        claimId={selectedClaimId}
        onClose={() => setSelectedClaimId(null)}
      />
    </div>
  );
}
