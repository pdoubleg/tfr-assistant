import { FilePlus2, Files, GitBranch, Plus } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { formCatalog } from "@/lib/mock-data";

export function FormCatalog() {
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_420px]">
      <Card>
        <CardHeader className="border-b">
          <div className="flex items-center justify-between gap-3">
            <CardTitle className="flex items-center gap-2">
              <Files className="h-4 w-4 text-primary" />
              Form Catalog
            </CardTitle>
            <Button size="sm" className="gap-1.5">
              <Plus className="h-4 w-4" />
              Register
            </Button>
          </div>
        </CardHeader>
        <CardContent className="grid gap-3 pt-5">
          {formCatalog.map((form) => (
            <div key={`${form.id}-${form.version}`} className="rounded-lg border bg-background p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-medium">{form.title}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{form.description}</p>
                </div>
                <Badge variant={form.status === "active" ? "success" : "warning"}>{form.status}</Badge>
              </div>
              <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted-foreground">
                <span className="rounded-md bg-secondary px-2 py-1">{form.id}</span>
                <span className="rounded-md bg-secondary px-2 py-1">{form.version}</span>
                <span className="rounded-md bg-secondary px-2 py-1">{form.questionCount} questions</span>
                <span className="rounded-md bg-secondary px-2 py-1">Updated {form.lastUpdated}</span>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="border-b">
          <CardTitle className="flex items-center gap-2">
            <FilePlus2 className="h-4 w-4 text-primary" />
            Register Questionnaire
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 pt-5">
          <div className="grid gap-2">
            <label className="text-sm font-medium" htmlFor="form-id">Form ID</label>
            <Input id="form-id" placeholder="interior_water" />
          </div>
          <div className="grid gap-2">
            <label className="text-sm font-medium" htmlFor="form-version">Version</label>
            <Input id="form-version" placeholder="v1.0" />
          </div>
          <div className="grid gap-2">
            <label className="text-sm font-medium" htmlFor="form-title">Title</label>
            <Input id="form-title" placeholder="Interior Water Loss Review" />
          </div>
          <div className="grid gap-2">
            <label className="text-sm font-medium" htmlFor="canonical-json">Canonical JSON</label>
            <Textarea id="canonical-json" className="min-h-[220px] font-mono text-xs" placeholder="{ ...AuditFormResult template... }" />
          </div>
          <Button className="w-full gap-2">
            <GitBranch className="h-4 w-4" />
            Save Draft Registration
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

