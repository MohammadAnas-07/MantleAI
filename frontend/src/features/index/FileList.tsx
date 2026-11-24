import { useId, useState } from "react";

import { QueryError } from "../../components/QueryError";
import { CONTROL } from "../../components/ui/Field";
import { Badge, Skeleton } from "../../components/ui/Feedback";
import { useDocuments } from "../../hooks/queries";

const FILTERS = [
  { value: "", label: "All" },
  { value: "indexed", label: "Indexed" },
  { value: "skipped", label: "Skipped" },
  { value: "pending", label: "Pending" },
];

/** The project's files with counts per status and the reason each skipped file was skipped. */
export function FileList({ projectId }: { projectId: string }) {
  const id = useId();
  const [filter, setFilter] = useState("");
  const documents = useDocuments(projectId, filter || null);

  const reasons = new Map<string, number>();
  for (const d of documents.data?.items ?? []) {
    if (d.skip_reason) reasons.set(d.skip_reason, (reasons.get(d.skip_reason) ?? 0) + 1);
  }

  return (
    <section aria-label="Files" className="space-y-2 border-t border-line pt-4">
      <div className="flex items-center gap-2">
        <h3 className="text-base">Files</h3>
        <label htmlFor={id} className="sr-only">
          Show
        </label>
        <select
          id={id}
          value={filter}
          onChange={(e) => {
            setFilter(e.target.value);
          }}
          className={`${CONTROL} ml-auto h-7 w-auto`}
        >
          {FILTERS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>
      </div>
      {documents.data ? (
        <p className="text-sm text-muted">
          {Object.entries(documents.data.counts)
            .map(([status, n]) => `${n} ${status}`)
            .join(", ") || "No files"}
        </p>
      ) : null}
      {reasons.size > 0 ? (
        <ul className="flex flex-wrap gap-1">
          {[...reasons].map(([reason, n]) => (
            <li key={reason}>
              <Badge kind="warning">
                {reason}: {n}
              </Badge>
            </li>
          ))}
        </ul>
      ) : null}
      {documents.isLoading ? <Skeleton label="Loading files" /> : null}
      {documents.isError ? (
        <QueryError
          error={documents.error}
          onRetry={() => void documents.refetch()}
          retrying={documents.isFetching}
        />
      ) : null}
      <ul className="code max-h-64 divide-y divide-line overflow-auto">
        {documents.data?.items.map((d) => (
          <li key={d.id} className="flex items-center gap-2 py-1">
            <span className="truncate" title={d.path}>
              {d.path}
            </span>
            {d.status !== "indexed" ? (
              <Badge kind={d.status === "skipped" ? "warning" : "info"}>
                {d.skip_reason ?? d.status}
              </Badge>
            ) : null}
          </li>
        ))}
      </ul>
      {documents.data && documents.data.total > documents.data.items.length ? (
        <p className="text-sm text-muted">
          Showing {documents.data.items.length} of {documents.data.total}.
        </p>
      ) : null}
    </section>
  );
}
