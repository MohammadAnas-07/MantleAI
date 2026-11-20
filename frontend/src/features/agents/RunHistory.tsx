import { Button } from "../../components/ui/Button";
import { useModelInfo } from "../../hooks/useModelInfo";
import { formatCost, formatDateTime, formatTokens } from "../../lib/format";
import type { AgentRun } from "../../lib/api/types";
import { RunStatusBadge } from "./RunBadges";
import { RUN_TYPE_LABEL } from "./runText";

/** Plan and review runs of the project, newest first. */
export function RunHistory({
  runs,
  shownId,
  onShow,
}: {
  runs: AgentRun[];
  shownId: string | null;
  onShow: (runId: string) => void;
}) {
  const models = useModelInfo();
  if (runs.length === 0) return <p className="text-sm text-muted">No agent runs yet.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Agent runs</caption>
        <thead>
          <tr className="label text-xs">
            <th scope="col">Time</th>
            <th scope="col">Type</th>
            <th scope="col">Status</th>
            <th scope="col">Model</th>
            <th scope="col">Tokens</th>
            <th scope="col">Cost</th>
            <th scope="col">
              <span className="sr-only">Open</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id} aria-current={r.id === shownId ? "true" : undefined}>
              <td>
                <time dateTime={r.created_at}>{formatDateTime(r.created_at)}</time>
              </td>
              <td>{RUN_TYPE_LABEL[r.run_type] ?? r.run_type}</td>
              <td>
                <RunStatusBadge status={r.status} />
              </td>
              <td>{models.name(r.model_id)}</td>
              <td>{formatTokens(r.input_tokens + r.output_tokens)}</td>
              <td>{formatCost(r.cost_usd)}</td>
              <td>
                <Button
                  size="sm"
                  aria-pressed={r.id === shownId}
                  aria-label={`Open the run from ${formatDateTime(r.created_at)}`}
                  onClick={() => {
                    onShow(r.id);
                  }}
                >
                  Open
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
