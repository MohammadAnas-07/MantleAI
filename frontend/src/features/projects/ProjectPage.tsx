import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState, type SubmitEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/Dialog";
import { FormError, SelectInput, TextInput } from "../../components/ui/Field";
import { QueryError } from "../../components/QueryError";
import { Skeleton } from "../../components/ui/Feedback";
import { PageHeader, Section } from "../../components/ui/PageHeader";
import { keys, useProject } from "../../hooks/queries";
import { useModelInfo } from "../../hooks/useModelInfo";
import { api } from "../../lib/api/endpoints";
import { ApiError, errorMessage, fieldErrors } from "../../lib/api/errors";
import { formatTokens } from "../../lib/format";
import { limits } from "../../lib/limits";
import type { Project } from "../../lib/api/types";

export function ProjectRoute() {
  const { projectId = "" } = useParams();
  return <ProjectPage key={projectId} projectId={projectId} />;
}

function ProjectPage({ projectId }: { projectId: string }) {
  const project = useProject(projectId);
  if (project.isLoading) return <Skeleton label="Loading the project" />;
  if (project.isError) {
    return (
      <QueryError
        error={project.error}
        onRetry={() => void project.refetch()}
        retrying={project.isFetching}
      />
    );
  }
  if (!project.data) return null;
  return (
    <div className="max-w-2xl space-y-8">
      <PageHeader
        title={project.data.name}
        description={
          <>
            Open a conversation in the explorer. Memory, the index and the profile are in the AI
            panel on the right. Stages, the gap finder and the Planner and Reviewer are on the{" "}
            <Link to={`/projects/${projectId}/workflow`}>workflow page</Link>.
          </>
        }
      />
      <ProjectSettings project={project.data} />
      <SourceFolder project={project.data} />
      <DeleteProject project={project.data} />
    </div>
  );
}

function ProjectSettings({ project }: { project: Project }) {
  const client = useQueryClient();
  const models = useModelInfo();
  const [name, setName] = useState(project.name);
  const [modelId, setModelId] = useState(project.default_model_id ?? "");
  const save = useMutation({
    mutationFn: () =>
      api.updateProject(project.id, { name: name.trim(), default_model_id: modelId || null }),
    onSuccess: (updated) => {
      client.setQueryData(keys.project(project.id), updated);
      void client.invalidateQueries({ queryKey: keys.projects });
    },
  });
  const errors = fieldErrors(save.error);
  const model = models.byId.get(modelId);
  const modelError =
    save.error instanceof ApiError && save.error.code === "model_unavailable"
      ? save.error.message
      : undefined;

  const submit = (event: SubmitEvent) => {
    event.preventDefault();
    if (name.trim()) save.mutate();
  };

  return (
    <Section id="project-settings" title="Project settings">
      <form onSubmit={submit} noValidate className="max-w-md space-y-4">
        <TextInput
          label="Name"
          value={name}
          maxLength={limits.projectName}
          onChange={(e) => {
            setName(e.target.value);
          }}
          error={!name.trim() ? "Give the project a name." : errors.name}
        />
        <SelectInput
          label="Default model"
          value={modelId}
          onChange={(e) => {
            setModelId(e.target.value);
          }}
          error={modelError}
          help={
            model && !models.hasKey(model)
              ? `Warning: no ${model.provider} key is saved. Conversations on this model won't work until you add one.`
              : "New conversations start on this model."
          }
        >
          <option value="">None</option>
          {models.chatModels.map((m) => (
            <option key={m.id} value={m.id}>
              {m.display_name} ({formatTokens(m.context_window)})
              {models.hasKey(m) ? "" : " - no key"}
            </option>
          ))}
        </SelectInput>
        <FormError
          message={save.isError && !modelError && !errors.name ? errorMessage(save.error) : null}
        />
        <div className="flex items-center gap-3">
          <Button type="submit" variant="primary" busy={save.isPending} disabled={!name.trim()}>
            Save
          </Button>
          {save.isSuccess ? (
            <p role="status" className="text-base text-success">
              Saved.
            </p>
          ) : null}
        </div>
      </form>
    </Section>
  );
}

function SourceFolder({ project }: { project: Project }) {
  const client = useQueryClient();
  const [path, setPath] = useState(project.root_path ?? "");
  const save = useMutation({
    mutationFn: () => api.setSource(project.id, path.trim()),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.project(project.id) });
      void client.invalidateQueries({ queryKey: keys.indexStatus(project.id) });
    },
  });
  return (
    <Section id="source-folder" title="Source folder">
      <form
        noValidate
        className="max-w-md space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (path.trim()) save.mutate();
        }}
      >
        <TextInput
          label="Folder path"
          value={path}
          maxLength={limits.path}
          spellCheck={false}
          placeholder="C:\code\my-app"
          onChange={(e) => {
            setPath(e.target.value);
          }}
          help="A new folder needs a new index run (AI panel, Index tab)."
          error={save.isError ? errorMessage(save.error) : undefined}
        />
        <Button
          type="submit"
          busy={save.isPending}
          disabled={!path.trim() || path.trim() === project.root_path}
        >
          Set folder
        </Button>
      </form>
    </Section>
  );
}

function DeleteProject({ project }: { project: Project }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const remove = useMutation({
    mutationFn: () => api.deleteProject(project.id),
    onSuccess: () => {
      setOpen(false);
      client.removeQueries({ queryKey: keys.project(project.id) });
      void client.invalidateQueries({ queryKey: keys.projects });
      void navigate("/");
    },
  });
  return (
    <Section id="danger-zone" title="Delete project">
      <p className="max-w-prose text-base text-muted">
        Deletes the project&apos;s conversations, memory and index from Mantle. Files in your folder
        are not touched.
      </p>
      <Button
        variant="danger"
        icon={<Trash2 aria-hidden className="size-4" />}
        onClick={() => {
          setOpen(true);
        }}
      >
        Delete project
      </Button>
      <ConfirmDialog
        title={`Delete "${project.name}"?`}
        open={open}
        danger
        onCancel={() => {
          setOpen(false);
        }}
        onConfirm={() => {
          remove.mutate();
        }}
        confirmLabel="Delete project"
        busy={remove.isPending}
        error={remove.isError ? errorMessage(remove.error) : null}
      >
        <p>
          Its conversations, memory and index are deleted. This can&apos;t be undone. Files in your
          folder are not touched.
        </p>
      </ConfirmDialog>
    </Section>
  );
}
