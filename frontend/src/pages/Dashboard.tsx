import { SummaryCards } from "@/components/dashboard/SummaryCards";
import { TrendChart } from "@/components/dashboard/TrendChart";
import { useClaims, useClaimTrends } from "@/hooks/useClaims";

export function Dashboard() {
  const { data, isLoading } = useClaims({ page_size: 1 });
  const { data: trends, isLoading: trendsLoading } = useClaimTrends();

  return (
    <div className="space-y-6">
      <SummaryCards stats={data?.stats} isLoading={isLoading} />
      <TrendChart data={trends?.data} isLoading={trendsLoading} />
    </div>
  );
}
