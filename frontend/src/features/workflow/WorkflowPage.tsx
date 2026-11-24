import type { ReactNode } from "react";
import { useParams } from "react-router";

import { PageHeader } from "../../components/ui/PageHeader";
import { useProject } from "../../hooks/queries";
import { AgentRunsSection } from "../agents/AgentRunsSection";
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
      <PageHeader
        title={`Workflow${project.data ? `: ${project.data.name}` : ""}`}
        description="Five stages, each approved by you. The gap finder and the Planner and Reviewer make model calls only when you start them, and save nothing until you approve."
      />
      <Section id="workflow-stages" title="Stages">
        <WorkflowSection projectId={projectId} />
      </Section>
      <Section id="gap-finder" title="Gap finder">
        <GapFinderPanel projectId={projectId} defaultModelId={defaultModelId} />
      </Section>
      <Section id="agent-runs" title="Planner and Reviewer">
        <AgentRunsSection projectId={projectId} defaultModelId={defaultModelId} />
      </Section>
    </div>
  );
}

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section
      aria-labelledby={id}
      className="space-y-4 border-t border-line pt-6 first-of-type:border-t-0 first-of-type:pt-0"
    >
      <h2 id={id} className="text-lg">
        {title}
      </h2>
      {children}
    </section>
  );
}
