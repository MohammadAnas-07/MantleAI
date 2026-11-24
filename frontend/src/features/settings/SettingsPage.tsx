import { PageHeader } from "../../components/ui/PageHeader";
import { KeysSection } from "./KeysSection";
import { ModelsSection } from "./ModelsSection";
import { UsageSection } from "./UsageSection";

export function SettingsPage() {
  return (
    <div className="max-w-4xl space-y-8 [&>section+section]:border-t [&>section+section]:border-line [&>section+section]:pt-8">
      <PageHeader
        title="Settings"
        description="Provider keys, the models Mantle may use, and what every model call has cost so far."
      />
      <KeysSection />
      <ModelsSection />
      <UsageSection />
    </div>
  );
}
