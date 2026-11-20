import { CircleCheck, CircleDot, Circle, SkipForward, type LucideIcon } from "lucide-react";

import type { Stage } from "../../lib/api/types";

const STATUS: Record<string, { Icon: LucideIcon; word: string }> = {
  current: { Icon: CircleDot, word: "current" },
  approved: { Icon: CircleCheck, word: "approved" },
  skipped: { Icon: SkipForward, word: "skipped" },
  pending: { Icon: Circle, word: "pending" },
};

/** The five stages in order. The current one is marked by an icon, a word and aria-current;
 * any stage can be opened to read or tick its checklist. */
export function StageBar({
  stages,
  viewing,
  onView,
}: {
  stages: Stage[];
  viewing: string;
  onView: (stageId: string) => void;
}) {
  return (
    <nav aria-label="Workflow stages">
      <ol className="flex flex-wrap gap-1">
        {stages.map((stage, i) => {
          const s = STATUS[stage.status] ?? STATUS.pending;
          const current = stage.status === "current";
          const selected = stage.id === viewing;
          return (
            <li key={stage.id}>
              <button
                type="button"
                onClick={() => {
                  onView(stage.id);
                }}
                aria-current={current ? "step" : undefined}
                aria-pressed={selected}
                className={`flex items-center gap-1.5 rounded-sm border-2 px-2 py-1 text-sm ${
                  current ? "bg-primary text-on-primary border-primary" : "border-line text-text"
                } ${selected && !current ? "border-accent" : ""}`}
              >
                {s ? <s.Icon aria-hidden className="size-4" /> : null}
                <span>
                  {i + 1}. {stage.title}
                </span>
                <span className="text-xs">({s?.word ?? stage.status})</span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
