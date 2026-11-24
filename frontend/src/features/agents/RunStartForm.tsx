import { useMutation } from "@tanstack/react-query";
import { useState, type SubmitEvent } from "react";

import { Button } from "../../components/ui/Button";
import { Banner } from "../../components/ui/Feedback";
import { Checkbox, SelectInput, TextArea } from "../../components/ui/Field";
import { useMemory } from "../../hooks/queries";
import { api } from "../../lib/api/endpoints";
import { ApiError } from "../../lib/api/errors";
import type { AgentRun, AgentRunStart, RunEstimate } from "../../lib/api/types";
import { limits } from "../../lib/limits";
import { startErrorText, suggestedModels } from "./runText";
import { CostGuardDialog, EstimateTable, ModelSelect, SuggestedModels } from "./shared";

type Source = "memory" | "text";

/**
 * Start a plan or review run. The estimate comes first (no model call); the run starts only
 * when the user confirms it. Changing any input drops the estimate, so the confirm always
 * matches what is sent.
 */
export function RunStartForm({
  projectId,
  modelId,
  onModelChange,
  onStarted,
  onBusy,
}: {
  projectId: string;
  modelId: string;
  onModelChange: (modelId: string) => void;
  onStarted: (run: AgentRun) => void;
  /** Called on 409 agent_run_in_progress: another tab started one. */
  onBusy: () => void;
}) {
  const requirements = useMemory(projectId, "requirement");
  const [runType, setRunType] = useState<"plan" | "review">("plan");
  const [source, setSource] = useState<Source>("memory");
  const [requirementId, setRequirementId] = useState("");
  const [text, setText] = useState("");
  const [useCode, setUseCode] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [costGuard, setCostGuard] = useState<RunEstimate | null>(null);

  const body: AgentRunStart = {
    run_type: runType,
    model_id: modelId,
    use_code_context: useCode,
    force: false,
    ...(runType === "plan"
      ? source === "memory"
        ? { requirement_id: requirementId }
        : { requirement_text: text.trim() }
      : {}),
  };
  const bodyKey = JSON.stringify(body);

  const estimate = useMutation({
    mutationFn: (sent: { body: AgentRunStart; key: string }) =>
      api.estimateAgentRun(projectId, sent.body),
  });
  // Shown only while it matches the inputs: the model can also change from outside the form
  // (a suggested model after a failed run).
  const shownEstimate =
    estimate.isSuccess && estimate.variables.key === bodyKey ? estimate.data : null;
  const start = useMutation({
    mutationFn: (force: boolean) => api.startAgentRun(projectId, { ...body, force }),
    onSuccess: (run) => {
      setCostGuard(null);
      estimate.reset();
      onStarted(run);
    },
    onError: (error) => {
      if (!(error instanceof ApiError)) return;
      if (error.code === "cost_limit_exceeded") {
        setCostGuard((error.details.estimate as RunEstimate | undefined) ?? null);
        return;
      }
      setCostGuard(null);
      if (error.code === "agent_run_in_progress") onBusy();
    },
  });

  const change =
    <T,>(set: (v: T) => void) =>
    (value: T) => {
      set(value);
      estimate.reset();
      start.reset();
      setFormError(null);
    };

  const submit = (event: SubmitEvent) => {
    event.preventDefault();
    const problem = !modelId
      ? "Choose a model."
      : runType === "plan" && source === "memory" && !requirementId
        ? "Choose the requirement to plan."
        : runType === "plan" && source === "text" && !text.trim()
          ? "Describe the requirement to plan."
          : null;
    setFormError(problem);
    if (problem) return;
    estimate.mutate({ body, key: bodyKey });
  };

  const error = start.error ?? estimate.error;
  const suggestions = error instanceof ApiError ? suggestedModels(error.details) : [];

  return (
    <form onSubmit={submit} noValidate className="space-y-3 rounded-lg border border-line p-4">
      <fieldset className="space-y-1">
        <legend className="text-base font-medium">Run type</legend>
        {(["plan", "review"] as const).map((t) => (
          <label key={t} className="flex items-center gap-2 text-base">
            <input
              type="radio"
              name="run-type"
              value={t}
              checked={runType === t}
              onChange={() => {
                change(setRunType)(t);
              }}
            />
            {t === "plan"
              ? "Plan: the Planner drafts tasks and decisions for a requirement, then the Reviewer checks them"
              : "Review: the Reviewer checks the current project memory"}
          </label>
        ))}
      </fieldset>

      {runType === "plan" ? (
        <fieldset className="space-y-2">
          <legend className="text-base font-medium">Requirement</legend>
          <div className="flex flex-wrap gap-3 text-base">
            {(["memory", "text"] as const).map((s) => (
              <label key={s} className="flex items-center gap-2">
                <input
                  type="radio"
                  name="requirement-source"
                  checked={source === s}
                  onChange={() => {
                    change(setSource)(s);
                  }}
                />
                {s === "memory" ? "Pick from memory" : "Write it here"}
              </label>
            ))}
          </div>
          {source === "memory" ? (
            <SelectInput
              label="Requirement from memory"
              value={requirementId}
              onChange={(e) => {
                change(setRequirementId)(e.target.value);
              }}
              help={
                requirements.data?.items.length === 0
                  ? "No requirements in memory yet. Add one in the Memory tab, or write it here."
                  : undefined
              }
            >
              <option value="">Choose a requirement</option>
              {requirements.data?.items.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.title}
                </option>
              ))}
            </SelectInput>
          ) : (
            <TextArea
              label="Requirement text"
              value={text}
              maxLength={limits.requirementText}
              onChange={(e) => {
                change(setText)(e.target.value);
              }}
              help={`${text.trim().length} of ${limits.requirementText} characters.`}
            />
          )}
        </fieldset>
      ) : null}

      <ModelSelect label="Run model" value={modelId} onChange={change(onModelChange)} />
      <Checkbox
        label="Use code context"
        checked={useCode}
        onChange={(e) => {
          change(setUseCode)(e.target.checked);
        }}
        help="Adds matching code from the index to the prompt. More tokens, so more cost. Off by default."
      />

      {formError ? (
        <p role="alert" className="text-base text-danger">
          {formError}
        </p>
      ) : null}
      <Button type="submit" busy={estimate.isPending}>
        Estimate cost
      </Button>

      {shownEstimate ? (
        <div aria-live="polite" className="space-y-2 rounded-lg border border-line p-2">
          <EstimateTable estimate={shownEstimate} />
          {shownEstimate.cost_usd === null ? (
            <Banner kind="warning">
              This model has no price in the catalog, so the cost limit can&apos;t be applied. Pick
              a model with prices.
            </Banner>
          ) : null}
          {shownEstimate.over_limit ? (
            <Banner kind="warning">
              This is above your cost limit. Starting needs a second confirm.
            </Banner>
          ) : null}
          <p className="text-sm text-muted">
            The run calls the model with your API key; your provider bills you. Nothing is saved to
            memory until you approve.
          </p>
          <Button
            variant={shownEstimate.over_limit ? "danger" : "primary"}
            busy={start.isPending}
            onClick={() => {
              if (shownEstimate.over_limit) setCostGuard(shownEstimate);
              else start.mutate(false);
            }}
          >
            {shownEstimate.over_limit ? "Start above the limit…" : "Confirm and start"}
          </Button>
        </div>
      ) : null}

      {error && !costGuard ? (
        <Banner kind="danger">
          {startErrorText(error)}
          <SuggestedModels models={suggestions} onPick={change(onModelChange)} />
        </Banner>
      ) : null}

      <CostGuardDialog
        estimate={costGuard}
        busy={start.isPending}
        onCancel={() => {
          setCostGuard(null);
        }}
        onForce={() => {
          start.mutate(true);
        }}
      />
    </form>
  );
}
