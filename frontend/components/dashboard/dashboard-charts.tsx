import { BarChart3, Gauge, ThumbsDown, ThumbsUp } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { reviews } from "@/lib/mock-data";
import { cn } from "@/lib/utils";

const metrics = [
  { label: "Forms reviewed", value: "128", change: "+18 this week", icon: BarChart3, tone: "cyan" },
  { label: "Edit rate", value: "34%", change: "User version differs", icon: Gauge, tone: "amber" },
  { label: "Positive feedback", value: String(reviews.filter((review) => review.feedback === "up").length), change: "Direct user signal", icon: ThumbsUp, tone: "emerald" },
  { label: "Needs review", value: String(reviews.filter((review) => review.feedback === "down").length), change: "Down votes or high edits", icon: ThumbsDown, tone: "rose" },
];

const outcomeData = [
  { label: "Meets", value: 48, className: "bg-emerald-500" },
  { label: "Does Not Meet", value: 52, className: "bg-rose-500" },
];

export function DashboardCharts() {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map((metric) => {
          const Icon = metric.icon;
          return (
            <Card key={metric.label}>
              <CardContent className="flex items-center gap-4 p-5">
                <div className={cn("flex h-10 w-10 items-center justify-center rounded-md border", toneClasses[metric.tone])}>
                  <Icon className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">{metric.label}</p>
                  <p className="text-2xl font-semibold">{metric.value}</p>
                  <p className="text-xs text-muted-foreground">{metric.change}</p>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card>
        <CardHeader className="border-b">
          <CardTitle>Outcome Mix</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 pt-5">
          {outcomeData.map((item) => (
            <div key={item.label} className="grid grid-cols-[130px_1fr_48px] items-center gap-3">
              <span className="text-sm font-medium">{item.label}</span>
              <div className="h-3 overflow-hidden rounded-full bg-secondary">
                <div className={cn("h-full rounded-full", item.className)} style={{ width: `${item.value}%` }} />
              </div>
              <span className="text-right text-sm tabular-nums text-muted-foreground">{item.value}%</span>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

const toneClasses: Record<string, string> = {
  cyan: "border-cyan-500/30 bg-cyan-500/10 text-cyan-700 dark:text-cyan-300",
  amber: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  emerald: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  rose: "border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300",
};
