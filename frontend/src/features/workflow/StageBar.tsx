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
      <ol className="flex flex-wrap gap-2">
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
                className={`flex h-8 items-center gap-1.5 rounded-sm border px-2.5 text-base transition-colors duration-150 ease-out ${
                  current ? "border-text" : "border-field font-normal"
                } ${selected ? "bg-hover" : "bg-paper hover:bg-hover"}`}
              >
                {s ? <s.Icon aria-hidden className="size-4 text-muted" /> : null}
                <span>
                  {i + 1}. {stage.title}
                </span>
                <span className="text-sm font-normal text-muted">({s?.word ?? stage.status})</span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
