import { CircleCheck, TriangleAlert } from "lucide-react";

import { Badge } from "../../components/ui/Feedback";
import type { MemoryIndex } from "../../hooks/useMemoryIndex";
import type { Review } from "../../lib/api/types";
import { SeverityBadge } from "./RunBadges";
import { References } from "./shared";

/** The Reviewer's verdict and findings. It only advises: the user decides. */
export function ReviewPanel({
  review,
  projectId,
  memory,
  planTitle,
}: {
  review: Review;
  projectId: string;
  memory: MemoryIndex;
  planTitle?: (ref: string) => string | undefined;
}) {
  const approve = review.verdict === "approve";
  return (
    <section aria-labelledby="review-title" className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <h3 id="review-title" className="text-base">
          Reviewer
        </h3>
        <Badge kind={approve ? "success" : "warning"}>
          {approve ? (
            <CircleCheck aria-hidden className="size-3" />
          ) : (
            <TriangleAlert aria-hidden className="size-3" />
          )}
          verdict: {approve ? "approve" : "changes requested"}
        </Badge>
      </div>
      {review.findings.length === 0 ? <p className="text-base text-muted">No findings.</p> : null}
      <ul aria-label="Reviewer findings" className="space-y-2">
        {review.findings.map((f, i) => (
          <li key={i} className="space-y-0.5 rounded-lg border border-line p-2 text-base">
            <SeverityBadge severity={f.severity} />
            <p className="whitespace-pre-wrap break-words" dir="auto">
              {f.explanation}
            </p>
            {f.suggestion ? (
              <p className="whitespace-pre-wrap break-words" dir="auto">
                <span className="eyebrow">Suggestion: </span>
                {f.suggestion}
              </p>
            ) : null}
            <References
              refs={f.refers_to}
              projectId={projectId}
              memory={memory}
              {...(planTitle ? { planTitle } : {})}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
