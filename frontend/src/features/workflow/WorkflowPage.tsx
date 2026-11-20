import type { ReactNode } from "react";
import { useParams } from "react-router";

import { useProject } from "../../hooks/queries";
import { GapFinderPanel } from "../agents/GapFinderPanel";
import { WorkflowSection } from "./WorkflowSection";

export function WorkflowRoute() {
  const { projectId = "" } = useParams();
  // Keyed by project: nothing from the previous project's page survives a switch.
  return <WorkflowPage key={projectId} projectId={projectId} />;
}

function WorkflowPage({ projectId }: { projectId: string }) {
  const project = useProject(projectId);
  const defaultModelId = project.data?.default_model_id;
  return (
    <div className="max-w-5xl space-y-8">
      <h1 className="text-xl">Workflow{project.data ? `: ${project.data.name}` : ""}</h1>
      <Section id="workflow-stages" title="Stages">
        <WorkflowSection projectId={projectId} />
      </Section>
      <Section id="gap-finder" title="Gap finder">
        <GapFinderPanel projectId={projectId} defaultModelId={defaultModelId} />
      </Section>
    </div>
  );
}

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="space-y-3">
      <h2 id={id} className="text-lg">
        {title}
      </h2>
      {children}
    </section>
  );
}
