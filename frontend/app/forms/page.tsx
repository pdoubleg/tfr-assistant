import { FormCatalog } from "@/components/forms/form-catalog";

export default function FormsPage() {
  return (
    <div className="mx-auto w-full max-w-7xl space-y-4 p-4 lg:p-6">
      <div>
        <h1 className="text-2xl font-semibold">Forms</h1>
        <p className="text-sm text-muted-foreground">View canonical questionnaires and register new audit form variants.</p>
      </div>
      <FormCatalog />
    </div>
  );
}

