// Small pieces shared by the gap finder and agent run views.

import { TriangleAlert } from "lucide-react";

import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/Dialog";
import { SelectInput } from "../../components/ui/Field";
import type { MemoryIndex } from "../../hooks/useMemoryIndex";
import { useModelInfo } from "../../hooks/useModelInfo";
import { formatCost, formatTokens } from "../../lib/format";
import type { RunEstimate, RunWarning, SuggestedModel } from "../../lib/api/types";
import { MemoryLink } from "../memory/MemoryLink";
import { warningText } from "./runText";

export function ModelSelect({
  value,
  onChange,
  label = "Model",
  help,
}: {
  value: string;
  onChange: (modelId: string) => void;
  label?: string;
  help?: string;
}) {
  const models = useModelInfo();
  return (
    <SelectInput
      label={label}
      value={value}
      help={help}
      onChange={(e) => {
        onChange(e.target.value);
      }}
    >
      <option value="">Choose a model</option>
      {models.chatModels.map((m) => (
        <option key={m.id} value={m.id}>
          {m.display_name}
          {models.hasKey(m) ? "" : " - no key"}
          {m.input_cost_per_mtok === null ? " - no price" : ""}
        </option>
      ))}
    </SelectInput>
  );
}

// The backend replaces references with real ids, but they started as model output: only a
// well-formed id becomes a link.
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Where a finding points: memory items link to their page; "task:N" and "decision:N" (items
 * of the draft plan) link to the item in the approval list.
 */
export function References({
  refs,
  projectId,
  memory,
  planTitle,
}: {
  refs: string[];
  projectId: string;
  memory: MemoryIndex;
  planTitle?: (ref: string) => string | undefined;
}) {
  if (refs.length === 0) return null;
  return (
    <p className="text-xs">
      <span className="label">Refers to: </span>
      {refs.map((ref, i) => {
        const plan = /^(task|decision):(\d+)$/.exec(ref);
        return (
          <span key={ref}>
            {i > 0 ? ", " : null}
            {plan ? (
              <a href={`#plan-${plan[1] ?? ""}-${plan[2] ?? ""}`} dir="auto">
                proposed {plan[1]}: {planTitle?.(ref) ?? `#${plan[2] ?? ""}`}
              </a>
            ) : UUID.test(ref) ? (
              <MemoryLink projectId={projectId} id={ref} index={memory} />
            ) : (
              <span dir="auto">{ref.slice(0, 40)}</span>
            )}
          </span>
        );
      })}
    </p>
  );
}

export function Warnings({ warnings }: { warnings: RunWarning[] }) {
  if (warnings.length === 0) return null;
  return (
    <ul aria-label="Warnings" className="space-y-1 text-sm">
      {warnings.map((w, i) => (
        <li key={i} className="flex items-start gap-1">
          <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
          <span>
            <span className="label">Warning: </span>
            {warningText(w)}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function EstimateTable({ estimate }: { estimate: RunEstimate }) {
  const rows: [string, string][] = [
    ["Model calls", `${estimate.steps} (plus at most one retry each)`],
    ["Input tokens", formatTokens(estimate.input_tokens)],
    ["Output tokens (upper bound)", formatTokens(estimate.output_tokens)],
    ["Cost (upper bound)", estimate.cost_usd === null ? "no price" : formatCost(estimate.cost_usd)],
    ["Your limit", formatCost(estimate.cost_limit_usd)],
  ];
  return (
    <table className="w-full text-left text-sm">
      <caption className="sr-only">Cost estimate</caption>
      <tbody>
        {rows.map(([k, v]) => (
          <tr key={k}>
            <th scope="row" className="label pr-2">
              {k}
            </th>
            <td>{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** The backend's 409 cost_limit_exceeded: show its numbers and ask before forcing. */
export function CostGuardDialog({
  estimate,
  onCancel,
  onForce,
  busy,
}: {
  estimate: RunEstimate | null;
  onCancel: () => void;
  onForce: () => void;
  busy: boolean;
}) {
  return (
    <ConfirmDialog
      title="Run above the cost limit?"
      open={estimate !== null}
      onCancel={onCancel}
      onConfirm={onForce}
      confirmLabel="Run anyway"
      danger
      busy={busy}
    >
      <p>
        This run could cost up to <strong>{formatCost(estimate?.cost_usd)}</strong>, above your
        limit of {formatCost(estimate?.cost_limit_usd)} (AGENT_RUN_COST_LIMIT_USD). It uses your key
        and your provider bills you.
      </p>
      {estimate ? <EstimateTable estimate={estimate} /> : null}
    </ConfirmDialog>
  );
}

/** Models the backend suggests after a context, rate or quota error. Picking one only
 * changes the form: Mantle never switches or starts by itself. */
export function SuggestedModels({
  models,
  onPick,
}: {
  models: SuggestedModel[];
  onPick?: (modelId: string) => void;
}) {
  if (models.length === 0) return null;
  return (
    <div className="space-y-1 text-sm">
      <p>Models that may work:</p>
      <ul className="flex flex-wrap gap-1">
        {models.map((m) => (
          <li key={m.model_id}>
            {onPick ? (
              <Button
                size="sm"
                onClick={() => {
                  onPick(m.model_id);
                }}
              >
                Use {m.display_name} ({formatTokens(m.context_window)})
              </Button>
            ) : (
              <span>
                {m.display_name} ({formatTokens(m.context_window)})
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
