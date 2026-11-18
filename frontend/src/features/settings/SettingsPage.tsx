import { KeysSection } from "./KeysSection";
import { ModelsSection } from "./ModelsSection";
import { UsageSection } from "./UsageSection";

export function SettingsPage() {
  return (
    <div className="max-w-4xl space-y-8">
      <h1 className="text-xl">Settings</h1>
      <KeysSection />
      <ModelsSection />
      <UsageSection />
    </div>
  );
}
