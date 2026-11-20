import {
  CircleCheck,
  CircleDashed,
  CircleSlash,
  CircleX,
  Hourglass,
  Loader2,
  UserCheck,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "../../components/ui/Feedback";
import type { Severity } from "../../lib/api/types";

type Kind = "neutral" | "info" | "warning" | "danger" | "success";

const STATUS: Record<string, { word: string; Icon: LucideIcon; kind: Kind; spin?: boolean }> = {
  queued: { word: "queued", Icon: Hourglass, kind: "neutral" },
  running: { word: "running", Icon: Loader2, kind: "info", spin: true },
  waiting_for_approval: { word: "waiting for your approval", Icon: UserCheck, kind: "warning" },
  approved: { word: "approved", Icon: CircleCheck, kind: "success" },
  completed: { word: "completed", Icon: CircleCheck, kind: "success" },
  rejected: { word: "rejected", Icon: CircleSlash, kind: "neutral" },
  cancelled: { word: "cancelled", Icon: CircleDashed, kind: "neutral" },
  failed: { word: "failed", Icon: CircleX, kind: "danger" },
};

/** A run status as an icon and a word (never colour alone). */
export function RunStatusBadge({ status }: { status: string }) {
  const s = STATUS[status] ?? { word: status, Icon: CircleDashed, kind: "neutral" as const };
  return (
    <Badge kind={s.kind}>
      <s.Icon aria-hidden className={`size-3 ${s.spin ? "animate-spin" : ""}`} />
      {s.word}
    </Badge>
  );
}

const SEVERITY: Record<Severity, Kind> = { high: "danger", medium: "warning", low: "neutral" };

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <Badge kind={SEVERITY[severity]}>{severity} severity</Badge>;
}
