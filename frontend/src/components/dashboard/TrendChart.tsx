import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { TrendPoint } from "@/schemas/claim";

interface TrendChartProps {
  data: TrendPoint[] | undefined;
  isLoading: boolean;
}

export function TrendChart({ data, isLoading }: TrendChartProps) {
  if (isLoading) {
    return (
      <div className="bg-card rounded-lg border border-border p-4">
        <div className="h-[250px] flex items-center justify-center">
          <div className="h-full w-full bg-muted rounded animate-pulse" />
        </div>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="bg-card rounded-lg border border-border p-4">
        <div className="h-[250px] flex items-center justify-center text-muted-foreground text-sm">
          Not enough data for trends yet.
        </div>
      </div>
    );
  }

  // Format dates for display
  const chartData = data.map((d) => ({
    ...d,
    label: new Date(d.date + "T00:00:00").toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    }),
  }));

  return (
    <div className="bg-card rounded-lg border border-border p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-foreground">
          Daily Claims Volume
        </h3>
        <span className="text-xs text-muted-foreground">Last 30 days</span>
      </div>
      <ResponsiveContainer width="100%" height={250}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(0 0% 18%)" />
          <XAxis
            dataKey="label"
            tick={{ fill: "hsl(0 0% 55%)", fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: "hsl(0 0% 18%)" }}
          />
          <YAxis
            tick={{ fill: "hsl(0 0% 55%)", fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: "hsl(0 0% 18%)" }}
            allowDecimals={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "hsl(0 0% 10%)",
              border: "1px solid hsl(0 0% 18%)",
              borderRadius: "0.375rem",
              color: "hsl(0 0% 88%)",
              fontSize: 12,
            }}
          />
          <Legend
            wrapperStyle={{ fontSize: 12, color: "hsl(0 0% 55%)" }}
          />
          <Line
            type="monotone"
            dataKey="success"
            stroke="hsl(142 71% 45%)"
            strokeWidth={2}
            dot={false}
            name="Success"
          />
          <Line
            type="monotone"
            dataKey="error"
            stroke="hsl(0 72% 51%)"
            strokeWidth={2}
            dot={false}
            name="Errors"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
