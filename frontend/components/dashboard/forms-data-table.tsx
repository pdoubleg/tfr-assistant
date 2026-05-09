"use client";

import { useMemo, useState } from "react";
import { ArrowDownUp, Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { AuditFormResult } from "@/lib/types";

export function FormsDataTable({ forms }: { forms: AuditFormResult[] }) {
  const [search, setSearch] = useState("");
  const filteredForms = useMemo(() => {
    const query = search.toLowerCase().trim();
    if (!query) return forms;
    return forms.filter((form) => form.title.toLowerCase().includes(query) || form.peril.peril.toLowerCase().includes(query));
  }, [forms, search]);

  return (
    <Card>
      <CardHeader className="border-b">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle>Saved Audit Forms</CardTitle>
          <div className="relative w-full sm:w-72">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input className="pl-9" placeholder="Search forms..." value={search} onChange={(event) => setSearch(event.target.value)} />
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow className="bg-secondary/60">
              <TableHead className="min-w-[220px]">
                <span className="flex items-center gap-1">Form <ArrowDownUp className="h-3 w-3" /></span>
              </TableHead>
              <TableHead>Peril</TableHead>
              <TableHead>Outcome</TableHead>
              <TableHead className="text-center">Questions</TableHead>
              <TableHead className="text-center">Drivers</TableHead>
              <TableHead>Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredForms.map((form) => {
              const driverCount = form.questions.reduce((count, question) => count + question.sub_questions.filter((sub) => sub.answer).length, 0);
              return (
                <TableRow key={form.id}>
                  <TableCell className="font-medium">{form.title}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{form.peril.peril}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={form.overall_outcome === "Meets" ? "success" : "danger"}>{form.overall_outcome}</Badge>
                  </TableCell>
                  <TableCell className="text-center tabular-nums">{form.questions.length}</TableCell>
                  <TableCell className="text-center tabular-nums">{driverCount}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{new Date(form.updated_at).toLocaleDateString()}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

