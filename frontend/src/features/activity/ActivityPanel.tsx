import { Activity } from "lucide-react";

import { Badge, EmptyState, Skeleton } from "../../components/ui/Feedback";
import { useUsageRecords } from "../../hooks/queries";
import { useModelInfo } from "../../hooks/useModelInfo";
import { QueryError } from "../../components/QueryError";
import { formatCost, formatTime, formatTokens, purposeLabel, sumCosts } from "../../lib/format";
import { Table } from "../../components/ui/Table";

// Calls since this tab opened: "this session".
const SESSION_START = new Date().toISOString();

/** Every model call of this session: chat, embeddings and background summaries alike. */
export function ActivityPanel() {
  const records = useUsageRecords(SESSION_START);
  const models = useModelInfo();
  const rows = records.data ?? [];

  if (records.isLoading) return <Skeleton lines={2} label="Loading activity" />;
  if (records.isError) {
    return (
      <QueryError
        error={records.error}
        onRetry={() => void records.refetch()}
        retrying={records.isFetching}
      />
    );
  }
  if (rows.length === 0)
    return (
      <EmptyState icon={Activity}>
        No model calls since this tab opened. Chat, indexing and summaries show up here.
      </EmptyState>
    );

  return (
    <div className="space-y-2 text-base">
      <p className="text-sm text-muted">
        {rows.length} calls, {formatCost(sumCosts(rows.map((r) => r.cost_usd)))} this session
      </p>
      <Table caption="Model calls this session">
        <thead>
          <tr>
            <th scope="col">Time</th>
            <th scope="col">Model</th>
            <th scope="col">Purpose</th>
            <th scope="col" className="num">
              Tokens in/out
            </th>
            <th scope="col" className="num">
              Cost
            </th>
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
              <td className="num">
                {formatTokens(r.input_tokens)}/{formatTokens(r.output_tokens)}
              </td>
              <td className="num">{formatCost(r.cost_usd)}</td>
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
      </Table>
    </div>
  );
}
