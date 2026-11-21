import { useState } from "react";

import { Badge } from "../../components/ui/Feedback";
import { Button } from "../../components/ui/Button";
import { formatDateTime } from "../../lib/format";
import type { Stage, WorkflowEvent } from "../../lib/api/types";

const ACTION: Record<string, string> = {
  created: "started the workflow",
  tick: "ticked",
  untick: "unticked",
  approve: "approved",
  skip: "skipped",
  reopen: "reopened",
  reset: "reset the workflow",
  completed: "completed the workflow",
};

const SHOWN = 20;

/** Who did what, when and why, newest first. */
export function EventHistory({
  events,
  total,
  stages,
}: {
  events: WorkflowEvent[];
  /** All events of the workflow; the API sends only the newest ones. */
  total: number;
  stages: Stage[];
}) {
  const [all, setAll] = useState(false);
  const titles = new Map(stages.map((s) => [s.id, s.title]));
  const items = new Map(stages.flatMap((s) => s.checklist.map((c) => [`${s.id}:${c.id}`, c.text])));
  const newest = [...events].reverse();
  const shown = all ? newest : newest.slice(0, SHOWN);

  if (events.length === 0) {
    return (
      <p className="text-sm text-muted">No changes yet. The first change starts the history.</p>
    );
  }
  return (
    <div className="space-y-2">
      <ol aria-label="Workflow history" className="space-y-1 text-sm">
        {shown.map((e) => {
          const stage = e.stage_id ? (titles.get(e.stage_id) ?? e.stage_id) : null;
          const item = e.stage_id && e.item_id ? items.get(`${e.stage_id}:${e.item_id}`) : null;
          return (
            <li key={e.id} className="border-b border-dashed border-line pb-1">
              <time dateTime={e.created_at} className="text-muted">
                {formatDateTime(e.created_at)}
              </time>{" "}
              <span className="label">{e.actor}</span> {ACTION[e.action] ?? e.action}
              {stage && !["created", "reset", "completed"].includes(e.action) ? ` "${stage}"` : ""}
              {item ? `: ${item}` : ""} {e.forced ? <Badge kind="warning">forced</Badge> : null}
              {e.reason ? (
                <p className="break-words" dir="auto">
                  <span className="label">Reason: </span>
                  {e.reason}
                </p>
              ) : null}
            </li>
          );
        })}
      </ol>
      {newest.length > SHOWN ? (
        <Button
          size="sm"
          onClick={() => {
            setAll((v) => !v);
          }}
        >
          {all ? "Show the latest 20" : `Show the latest ${newest.length}`}
        </Button>
      ) : null}
      {all && total > newest.length ? (
        <p className="text-xs text-muted">
          The {total - newest.length} oldest of {total} events are not shown.
        </p>
      ) : null}
    </div>
  );
}
