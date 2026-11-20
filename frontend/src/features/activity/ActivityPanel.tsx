import { Activity } from "lucide-react";

import { Badge, EmptyState, Skeleton } from "../../components/ui/Feedback";
import { useUsageRecords } from "../../hooks/queries";
import { useModelInfo } from "../../hooks/useModelInfo";
import { errorMessage } from "../../lib/api/errors";
import { formatCost, formatTime, formatTokens, purposeLabel, sumCosts } from "../../lib/format";

// Calls since this tab opened: "this session".
const SESSION_START = new Date().toISOString();

/** Every model call of this session: chat, embeddings and background summaries alike. */
export function ActivityPanel() {
  const records = useUsageRecords(SESSION_START);
  const models = useModelInfo();
  const rows = records.data ?? [];

  if (records.isLoading) return <Skeleton lines={2} label="Loading activity" />;
  if (records.isError) return <p className="text-sm text-danger">{errorMessage(records.error)}</p>;
  if (rows.length === 0)
    return <EmptyState icon={Activity}>No model calls in this session yet.</EmptyState>;

  return (
    <div className="space-y-1 text-sm">
      <p className="text-muted">
        {rows.length} calls, {formatCost(sumCosts(rows.map((r) => r.cost_usd)))} this session
      </p>
      <table className="w-full text-left">
        <caption className="sr-only">Model calls this session</caption>
        <thead>
          <tr className="label text-xs">
            <th scope="col">Time</th>
            <th scope="col">Model</th>
            <th scope="col">Purpose</th>
            <th scope="col">Tokens in/out</th>
            <th scope="col">Cost</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{formatTime(r.created_at)}</td>
              <td>{models.name(r.model_id)}</td>
              <td>
                {purposeLabel(r.purpose)}{" "}
                {r.trigger === "background" ? <Badge kind="info">background</Badge> : null}
              </td>
              <td>
                {formatTokens(r.input_tokens)}/{formatTokens(r.output_tokens)}
              </td>
              <td>{formatCost(r.cost_usd)}</td>
              <td>
                {r.status === "success" ? (
                  "ok"
                ) : (
                  <Badge kind="danger">{r.error_code ?? r.status}</Badge>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
