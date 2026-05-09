import { DashboardCharts } from "@/components/dashboard/dashboard-charts";
import { FormsDataTable } from "@/components/dashboard/forms-data-table";
import { QuestionsAggregationTable } from "@/components/dashboard/questions-aggregation-table";
import { aggregatedQuestions, savedForms } from "@/lib/mock-data";

export default function DashboardPage() {
  return (
    <div className="mx-auto w-full max-w-7xl space-y-4 p-4 lg:p-6">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-sm text-muted-foreground">Audit volume, output quality, and question-level analytics.</p>
      </div>
      <DashboardCharts />
      <FormsDataTable forms={savedForms} />
      <QuestionsAggregationTable questions={aggregatedQuestions} />
    </div>
  );
}

