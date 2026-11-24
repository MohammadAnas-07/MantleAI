import { useId, useState } from "react";

import { Badge, Skeleton } from "../../components/ui/Feedback";
import { useDocuments } from "../../hooks/queries";
import { errorMessage } from "../../lib/api/errors";

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
    <section aria-label="Files" className="space-y-2">
      <div className="flex items-center gap-2">
        <h3 className="text-sm">Files</h3>
        <label htmlFor={id} className="sr-only">
          Show
        </label>
        <select
          id={id}
          value={filter}
          onChange={(e) => {
            setFilter(e.target.value);
          }}
          className="ml-auto rounded-sm border border-field bg-paper px-1 text-sm"
        >
          {FILTERS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>
      </div>
      {documents.data ? (
        <p className="text-muted">
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
      {documents.isError ? <p className="text-danger">{errorMessage(documents.error)}</p> : null}
      <ul className="code max-h-64 space-y-0.5 overflow-auto">
        {documents.data?.items.map((d) => (
          <li key={d.id} className="flex items-center gap-2">
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
        <p className="text-muted">
          Showing {documents.data.items.length} of {documents.data.total}.
        </p>
      ) : null}
    </section>
  );
}
