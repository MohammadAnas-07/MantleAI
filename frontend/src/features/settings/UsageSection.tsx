import { Badge, Banner, Skeleton } from "../../components/ui/Feedback";
import { useUsage } from "../../hooks/queries";
import { useModelInfo } from "../../hooks/useModelInfo";
import { errorMessage } from "../../lib/api/errors";
import { formatCost, formatTokens, purposeLabel, sumCosts } from "../../lib/format";
import type { UsageLine } from "../../lib/api/types";

interface Row {
  key: string;
  label: string;
  background: boolean;
  calls: number;
  tokens: number;
  cost: number;
}

function group(
  lines: UsageLine[],
  keyOf: (l: UsageLine) => string,
  labelOf: (l: UsageLine) => string,
): Row[] {
  const rows = new Map<string, Row & { costs: (string | null)[] }>();
  for (const line of lines) {
    const key = keyOf(line);
    const row = rows.get(key) ?? {
      key,
      label: labelOf(line),
      background: line.trigger === "background",
      calls: 0,
      tokens: 0,
      cost: 0,
      costs: [],
    };
    row.calls += line.calls;
    row.tokens += line.input_tokens + line.output_tokens;
    row.costs.push(line.cost_usd);
    rows.set(key, row);
  }
  return [...rows.values()]
    .map(({ costs, ...row }) => ({ ...row, cost: sumCosts(costs) }))
    .sort((a, b) => b.cost - a.cost || a.label.localeCompare(b.label));
}

/** Cost by model and by purpose, so background summaries and embeddings show on their own. */
export function UsageSection() {
  const usage = useUsage();
  const models = useModelInfo();
  if (usage.isLoading) return <Skeleton label="Loading usage" />;
  if (usage.isError) return <Banner kind="danger">{errorMessage(usage.error)}</Banner>;
  const lines = usage.data?.lines ?? [];
  const byModel = group(
    lines,
    (l) => l.model_id,
    (l) => models.name(l.model_id),
  );
  const byPurpose = group(
    lines,
    (l) => `${l.purpose}:${l.trigger}`,
    (l) => purposeLabel(l.purpose),
  );

  return (
    <section aria-labelledby="usage-title" className="space-y-3">
      <h2 id="usage-title" className="text-base">
        Usage
      </h2>
      <p className="text-sm">
        {usage.data?.total_calls ?? 0} calls,{" "}
        {formatTokens(
          (usage.data?.total_input_tokens ?? 0) + (usage.data?.total_output_tokens ?? 0),
        )}{" "}
        tokens, {formatCost(usage.data?.total_cost_usd)} in total
      </p>
      <div className="grid gap-4 md:grid-cols-2">
        <UsageTable title="By model" rows={byModel} />
        <UsageTable title="By purpose" rows={byPurpose} />
      </div>
    </section>
  );
}

function UsageTable({ title, rows }: { title: string; rows: Row[] }) {
  return (
    <table className="w-full text-left text-sm">
      <caption className="label text-left">{title}</caption>
      <thead>
        <tr className="label text-xs">
          <th scope="col">Name</th>
          <th scope="col">Calls</th>
          <th scope="col">Tokens</th>
          <th scope="col">Cost</th>
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 ? (
          <tr>
            <td colSpan={4} className="text-muted">
              No calls yet.
            </td>
          </tr>
        ) : null}
        {rows.map((r) => (
          <tr key={r.key}>
            <td>
              {r.label} {r.background ? <Badge kind="info">background</Badge> : null}
            </td>
            <td>{r.calls}</td>
            <td>{formatTokens(r.tokens)}</td>
            <td>{formatCost(r.cost)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
