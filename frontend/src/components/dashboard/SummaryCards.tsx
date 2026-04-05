import { TrendingUp, AlertCircle, Clock, CheckCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ClaimStats } from "@/schemas/claim";

interface SummaryCardsProps {
  stats: ClaimStats | undefined;
  isLoading: boolean;
}

interface CardProps {
  title: string;
  value: string | number;
  icon: React.ReactNode;
  color?: string;
  isLoading: boolean;
}

function Card({ title, value, icon, color, isLoading }: CardProps) {
  return (
    <div className="bg-card rounded-lg border border-border p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {title}
        </span>
        <span className={cn("text-muted-foreground", color)}>{icon}</span>
      </div>
      {isLoading ? (
        <div className="h-8 w-20 bg-muted rounded animate-pulse" />
      ) : (
        <p className="text-2xl font-semibold text-foreground">{value}</p>
      )}
    </div>
  );
}

export function SummaryCards({ stats, isLoading }: SummaryCardsProps) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <Card
        title="Total Claims"
        value={stats?.total ?? 0}
        icon={<CheckCircle size={18} />}
        isLoading={isLoading}
      />
      <Card
        title="Success Rate"
        value={
          stats?.success_rate != null
            ? `${(stats.success_rate * 100).toFixed(1)}%`
            : "--"
        }
        icon={<TrendingUp size={18} />}
        color="text-success"
        isLoading={isLoading}
      />
      <Card
        title="Errors"
        value={stats?.error ?? 0}
        icon={<AlertCircle size={18} />}
        color="text-destructive"
        isLoading={isLoading}
      />
      <Card
        title="Pending"
        value={stats?.pending ?? 0}
        icon={<Clock size={18} />}
        color="text-warning"
        isLoading={isLoading}
      />
    </div>
  );
}
