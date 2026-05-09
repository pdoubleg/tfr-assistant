import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { AggregatedQuestion } from "@/lib/types";

export function QuestionsAggregationTable({ questions }: { questions: AggregatedQuestion[] }) {
  return (
    <Card>
      <CardHeader className="border-b">
        <CardTitle>Question Analytics</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow className="bg-secondary/60">
              <TableHead className="w-16">ID</TableHead>
              <TableHead className="min-w-[260px]">Question</TableHead>
              <TableHead className="text-center">Yes</TableHead>
              <TableHead className="text-center">No</TableHead>
              <TableHead className="text-center">Insuff.</TableHead>
              <TableHead className="text-center">Edits</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {questions.map((question) => (
              <TableRow key={question.id}>
                <TableCell className="font-mono text-xs font-semibold text-primary">{question.id}</TableCell>
                <TableCell>{question.text}</TableCell>
                <TableCell className="text-center"><Badge variant="success">{question.yesCount}</Badge></TableCell>
                <TableCell className="text-center"><Badge variant="danger">{question.noCount}</Badge></TableCell>
                <TableCell className="text-center"><Badge variant="warning">{question.insufficientCount}</Badge></TableCell>
                <TableCell className="text-center tabular-nums">{question.editCount}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

