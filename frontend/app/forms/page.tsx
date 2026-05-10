import { FormCatalog } from "@/components/forms/form-catalog";

export default function FormsPage() {
  return (
    <div className="mx-auto w-full max-w-[1600px] space-y-4 px-3 py-4 lg:px-4 lg:py-5">
      <div>
        <h1 className="text-2xl font-semibold">Forms</h1>
        <p className="text-sm text-muted-foreground">View canonical questionnaires and register new audit form variants.</p>
      </div>
      <FormCatalog />
    </div>
  );
}
