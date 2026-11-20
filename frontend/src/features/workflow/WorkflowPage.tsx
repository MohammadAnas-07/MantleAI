import { useParams } from "react-router";

import { WorkflowSection } from "./WorkflowSection";

export function WorkflowRoute() {
  const { projectId = "" } = useParams();
  // Keyed by project: nothing from the previous project's page survives a switch.
  return <WorkflowPage key={projectId} projectId={projectId} />;
}

function WorkflowPage({ projectId }: { projectId: string }) {
  return (
    <div className="max-w-5xl space-y-8">
      <h1 className="text-xl">Workflow</h1>
      <section aria-labelledby="workflow-stages" className="space-y-3">
        <h2 id="workflow-stages" className="text-lg">
          Stages
        </h2>
        <WorkflowSection projectId={projectId} />
      </section>
    </div>
  );
}
