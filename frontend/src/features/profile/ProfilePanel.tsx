import { FileSearch } from "lucide-react";

import { Badge, Banner, EmptyState, Skeleton } from "../../components/ui/Feedback";
import { useProfile } from "../../hooks/queries";
import { errorMessage } from "../../lib/api/errors";
import type { ProjectProfile } from "../../lib/api/types";
import { formatDateTime } from "../../lib/format";

const OUT_OF_DATE: Record<string, string> = {
  source_changed: "the project folder changed since it was built",
  index_changed: "a later index run ended without rebuilding it",
};

/**
 * The project profile: facts read from the files at the end of the last successful index
 * run, without a model. Every value comes from the repository, so it is shown as plain text
 * (React escapes it); nothing here is a link or HTML.
 */
export function ProfilePanel({ projectId }: { projectId: string }) {
  const profile = useProfile(projectId);
  if (profile.isLoading) return <Skeleton label="Loading the project profile" />;
  if (profile.isError) return <Banner kind="danger">{errorMessage(profile.error)}</Banner>;
  const p = profile.data;
  if (!p) return null;
  if (!p.built) {
    return (
      <EmptyState icon={FileSearch}>
        No profile yet. It is built from the project files, without a model, at the end of each
        successful index run. Index the project in the Index tab.
      </EmptyState>
    );
  }
  return (
    <div className="space-y-3 text-sm">
      <div role="status" aria-live="polite" className="space-y-2">
        <p>
          Built {formatDateTime(p.built_at)} from the files, no model. Every model you chat with
          gets this profile.
        </p>
        {p.out_of_date ? (
          <Banner kind="warning">
            The profile may be out of date:{" "}
            {p.out_of_date_reasons.map((r) => OUT_OF_DATE[r] ?? r).join("; ")}. Index the project
            again to rebuild it.
          </Banner>
        ) : null}
      </div>
      <Languages profile={p} />
      <Facts title="Frameworks" items={p.frameworks.map((f) => [f.name, f.source])} />
      <Facts
        title="Commands"
        items={p.commands.map((c) => [`${c.name}: ${c.command}`, c.source, c.kind === "inferred"])}
      />
      <Facts title="Markers" items={p.markers.map((m) => [m.name, m.source])} />
      <Facts title="Manifests" items={p.manifests.map((m) => [m.kind, m.source])} />
      <Facts
        title="Dependencies"
        items={p.dependencies.map((d) => [d.dev ? `${d.name} (dev)` : d.name, d.source])}
      />
      <Facts title="Entry points" items={p.entry_points.map((e) => [e.source, e.kind])} />
      <Facts title="Folders" items={p.layout.map((l) => [l.path, `${String(l.files)} files`])} />
    </div>
  );
}

function Languages({ profile }: { profile: ProjectProfile }) {
  if (profile.languages.length === 0) return null;
  return (
    <section aria-label="Languages" className="space-y-1">
      <h3 className="label text-xs">Languages</h3>
      <ul className="flex flex-wrap gap-2">
        {profile.languages.map((l) => (
          <li key={l.name}>
            <Badge>
              {l.name} {Math.round(l.share * 100)}% · {l.files}
            </Badge>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** One fact per row: the value, then the file it was read from. */
function Facts({ title, items }: { title: string; items: [string, string, boolean?][] }) {
  if (items.length === 0) return null;
  return (
    <section aria-label={title} className="space-y-1">
      <h3 className="label text-xs">
        {title} ({items.length})
      </h3>
      <ul className="space-y-0.5">
        {items.map(([value, source, inferred]) => (
          <li key={`${value}|${source}`} className="flex flex-wrap items-baseline gap-x-2">
            <span className="code break-all">{value}</span>
            <span className="text-xs break-all text-muted">{source}</span>
            {inferred ? <Badge>inferred</Badge> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
