import { Button } from "../../components/ui/Button";
import { useModelInfo } from "../../hooks/useModelInfo";
import { formatCost, formatDateTime, formatTokens } from "../../lib/format";
import type { AgentRunSummary } from "../../lib/api/types";
import { RunStatusBadge } from "./RunBadges";
import { RUN_TYPE_LABEL } from "./runText";
import { Table } from "../../components/ui/Table";

/** Plan and review runs of the project, newest first. */
export function RunHistory({
  runs,
  shownId,
  onShow,
}: {
  runs: AgentRunSummary[];
  shownId: string | null;
  onShow: (runId: string) => void;
}) {
  const models = useModelInfo();
  if (runs.length === 0) return <p className="text-base text-muted">No agent runs yet.</p>;
  return (
    <Table caption="Agent runs">
      <thead>
        <tr>
          <th scope="col">Time</th>
          <th scope="col">Type</th>
          <th scope="col">Status</th>
          <th scope="col">Model</th>
          <th scope="col" className="num">
            Tokens
          </th>
          <th scope="col" className="num">
            Cost
          </th>
          <th scope="col">
            <span className="sr-only">Open</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {runs.map((r) => (
          <tr
            key={r.id}
            aria-current={r.id === shownId ? "true" : undefined}
            className={r.id === shownId ? "bg-hover" : undefined}
          >
            <td>
              <time dateTime={r.created_at}>{formatDateTime(r.created_at)}</time>
            </td>
            <td>{RUN_TYPE_LABEL[r.run_type] ?? r.run_type}</td>
            <td>
              <RunStatusBadge status={r.status} />
            </td>
            <td>{models.name(r.model_id)}</td>
            <td className="num">{formatTokens(r.input_tokens + r.output_tokens)}</td>
            <td className="num">{formatCost(r.cost_usd)}</td>
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
    </Table>
  );
}
